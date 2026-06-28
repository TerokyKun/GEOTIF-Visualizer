using System;
using System.IO.MemoryMappedFiles;
using System.Threading;
using System.Threading.Tasks;
using KensVisualizer.Models;
using KensVisualizer.ViewModels;

namespace KensVisualizer.Services
{
    public class SharedMemoryReader : IDisposable
    {
        private MemoryMappedFile? _mmf;
        private MemoryMappedViewAccessor? _accessor;
        private readonly string _name;
        private bool _disposed;

        public SharedMemoryReader(string name = "kens_shm") { _name = name; }

        public bool Open()
        {
            try
            {
                _mmf = MemoryMappedFile.OpenExisting(_name, MemoryMappedFileRights.Read);
                _accessor = _mmf.CreateViewAccessor(0, 0, MemoryMappedFileAccess.Read);
                return true;
            }
            catch { return false; }
        }

        public bool Read(out SharedMemoryLayout layout)
        {
            layout = default;
            if (_accessor == null) return false;
            try { _accessor.Read(0, out layout); return layout.IsValid; }
            catch { return false; }
        }

        public void Dispose()
        {
            if (_disposed) return;
            _accessor?.Dispose(); _mmf?.Dispose(); _disposed = true;
        }
    }

    public class TelemetryPoller : IDisposable
    {
        private readonly SharedMemoryReader _reader;
        private CancellationTokenSource? _cts;
        private Task? _pollTask;
        private bool _disposed;
        private readonly int _intervalMs;
        private bool _wasConnected;

        public event Action<SharedMemoryLayout>? DataReceived;
        public event Action<bool>? ConnectionChanged;

        public TelemetryPoller(string shmName = "kens_shm", int intervalMs = 100)
        {
            _reader = new SharedMemoryReader(shmName);
            _intervalMs = intervalMs;
        }

        public bool Start()
        {
            _cts = new CancellationTokenSource();
            _pollTask = Task.Run(async () =>
            {
                // Цикл: ждём пока shared memory появится
                while (!_cts.Token.IsCancellationRequested)
                {
                    if (_reader.Open())
                    {
                        // Shared memory найдена — читаем данные
                        while (!_cts.Token.IsCancellationRequested)
                        {
                            if (_reader.Read(out var layout))
                            {
                                MainWindow._vm.IsConnected = true;
                                MainWindow._vm.StatusText = "CONNECT";
                                DataReceived?.Invoke(layout);
                            }
                            else
                            {
                                MainWindow._vm.StatusText = "DISCONNECT";
                                MainWindow._vm.IsConnected = false;
                            }
                            await Task.Delay(_intervalMs, _cts.Token).ConfigureAwait(false);
                        }
                    }
                    // C++ не запущен — повторяем каждые 500мс
                    await Task.Delay(500, _cts.Token).ConfigureAwait(false);
                }
            }, _cts.Token);
            return true;
        }

        public void Dispose()
        {
            if (_disposed) return;
            _cts?.Cancel(); _reader.Dispose(); _cts?.Dispose(); _disposed = true;
        }
    }
}