using System;
using System.IO.MemoryMappedFiles;
using System.Runtime.InteropServices;
using System.Threading;
using KensVisualizer.Models;

namespace KensVisualizer.Services
{
    public class DemoSimulator : IDisposable
    {
        private MemoryMappedFile? _mmf;
        private MemoryMappedViewAccessor? _accessor;
        private Timer? _timer;
        private double _t, _x = 5000, _y = 5000, _vx = 50, _vy, _heading;
        private bool _disposed;

        public void Start(string shmName = "kens_shm", int intervalMs = 100)
        {
            try
            {
                int sz = Marshal.SizeOf<SharedMemoryLayout>();
                _mmf = MemoryMappedFile.CreateOrOpen(shmName, sz);
                _accessor = _mmf.CreateViewAccessor();
            }
            catch { return; }
            _timer = new Timer(OnTick, null, 0, intervalMs);
        }

        private void OnTick(object? _)
        {
            if (_accessor == null) return;
            double dt = 0.1;
            double nx = 0.01 * (Random.Shared.NextDouble() * 2 - 1);
            double ny = 0.01 * (Random.Shared.NextDouble() * 2 - 1);
            _x += (_vx + nx) * dt; _y += (_vy + ny) * dt;
            if (_t > 5 && _t < 15) { _heading += 0.05 * dt; _vx = 50 * Math.Cos(_heading); _vy = 50 * Math.Sin(_heading); }

            long o = 0;
            _accessor.Write(o, 0x4B454E53u); o += 4;
            _accessor.Write(o, 2u); o += 4;
            _accessor.Write(o, (ulong)(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() * 1000)); o += 8;
            _accessor.Write(o, _x); o += 8; _accessor.Write(o, _y); o += 8;
            _accessor.Write(o, _vx); o += 8; _accessor.Write(o, _vy); o += 8;
            _accessor.Write(o, _heading); o += 8; _accessor.Write(o, 100.0); o += 8;
            _accessor.Write(o, _x + 2 * Math.Sin(_t * 0.3)); o += 8;
            _accessor.Write(o, _y + 1.5 * Math.Cos(_t * 0.3)); o += 8;
            _accessor.Write(o, 2 * Math.Sin(_t * 0.3)); o += 8;
            _accessor.Write(o, 1.5 * Math.Cos(_t * 0.3)); o += 8;
            _accessor.Write(o, (byte)1); o += 1;
            _accessor.Write(o, _x + 0.5 * Math.Sin(_t * 0.2)); o += 8;
            _accessor.Write(o, _y + 0.3 * Math.Cos(_t * 0.2)); o += 8;
            _accessor.Write(o, _vx); o += 8; _accessor.Write(o, _vy); o += 8;
            _accessor.Write(o, 0.01 * Math.Sin(_t * 0.1)); o += 8;
            _accessor.Write(o, 0.01 * Math.Cos(_t * 0.1)); o += 8;
            _accessor.Write(o, 0.0); o += 8;
            _accessor.Write(o, 1.5); o += 8; _accessor.Write(o, 1.2); o += 8;
            _accessor.Write(o, (byte)1); o += 1;
            _accessor.Write(o, 0.5 * Math.Sin(_t * 0.1)); o += 8;
            _accessor.Write(o, 0.48 * Math.Sin(_t * 0.1)); o += 8;
            _accessor.Write(o, 2.5); o += 8; _accessor.Write(o, 1.8); o += 8;
            _accessor.Write(o, 0.7); o += 8;
            _accessor.Write(o, 0.0); o += 8; _accessor.Write(o, 0.0); o += 8;
            _accessor.Write(o, 1.0); o += 8; _accessor.Write(o, -1.0); o += 8;
            _accessor.Write(o, 1000); o += 4; _accessor.Write(o, 1000); o += 4;
            _accessor.Write(o, 0); o += 4; _accessor.Write(o, 0); o += 4;
            _accessor.Write(o, 0.0); o += 8; _accessor.Write(o, 0.0); o += 8;
            for (int i = 0; i < 65536; i++) { _accessor.Write(o, (byte)0); o += 1; }
            _accessor.Write(o, (byte)1); o += 1;
            _accessor.Write(o, (byte)0); o += 1;
            _accessor.Write(o, (byte)0); o += 1;
            _accessor.Write(o, 32.0); o += 8; _accessor.Write(o, 8.0); o += 8;
            _accessor.Write(o, 0.01); o += 8; _accessor.Write(o, 0.7); o += 8;
            _t += dt;
        }

        public void Dispose()
        {
            if (_disposed) return;
            _timer?.Dispose(); _accessor?.Dispose(); _mmf?.Dispose(); _disposed = true;
        }
    }
}
