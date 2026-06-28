using System.Windows;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using KensVisualizer.Models;
using KensVisualizer.Services;

namespace KensVisualizer.ViewModels
{
    public class MainViewModel : INotifyPropertyChanged, IDisposable
    {
        private readonly TelemetryPoller _poller;
        private bool _disposed;

        public ObservableCollection<TrajectoryPoint> InsTrajectory { get; } = new();
        public ObservableCollection<TrajectoryPoint> KensTrajectory { get; } = new();
        public ObservableCollection<TrajectoryPoint> EkfTrajectory { get; } = new();

        public double InsX { get => _insX; set { _insX = value; OnPropertyChanged(); } }
        public double InsY { get => _insY; set { _insY = value; OnPropertyChanged(); } }
        public double InsVx { get => _insVx; set { _insVx = value; OnPropertyChanged(); } }
        public double InsVy { get => _insVy; set { _insVy = value; OnPropertyChanged(); } }
        public double InsHeading { get => _insHeading; set { _insHeading = value; OnPropertyChanged(); } }
        public double InsAltitude { get => _insAltitude; set { _insAltitude = value; OnPropertyChanged(); } }

        public double KensX { get => _kensX; set { _kensX = value; OnPropertyChanged(); } }
        public double KensY { get => _kensY; set { _kensY = value; OnPropertyChanged(); } }
        public double KensDeltaX { get => _kensDeltaX; set { _kensDeltaX = value; OnPropertyChanged(); } }
        public double KensDeltaY { get => _kensDeltaY; set { _kensDeltaY = value; OnPropertyChanged(); } }
        public bool KensValid { get => _kensValid; set { _kensValid = value; OnPropertyChanged(); } }
        public bool KensFallback { get => _kensFallback; set { _kensFallback = value; OnPropertyChanged(); } }
        public bool KensInBounds { get => _kensInBounds; set { _kensInBounds = value; OnPropertyChanged(); } }
        public double KensDhError { get => _kensDhError; set { _kensDhError = value; OnPropertyChanged(); } }
        public double KensLp { get => _kensLp; set { _kensLp = value; OnPropertyChanged(); } }
        public double KensSearchWindowHalf { get => _kensSearchWindowHalf; set { _kensSearchWindowHalf = value; OnPropertyChanged(); } }
        public double KensRefBlockSize { get => _kensRefBlockSize; set { _kensRefBlockSize = value; OnPropertyChanged(); } }

        public double EkfX { get => _ekfX; set { _ekfX = value; OnPropertyChanged(); } }
        public double EkfY { get => _ekfY; set { _ekfY = value; OnPropertyChanged(); } }
        public double EkfVx { get => _ekfVx; set { _ekfVx = value; OnPropertyChanged(); } }
        public double EkfVy { get => _ekfVy; set { _ekfVy = value; OnPropertyChanged(); } }
        public double EkfSigmaX { get => _ekfSigmaX; set { _ekfSigmaX = value; OnPropertyChanged(); } }
        public double EkfSigmaY { get => _ekfSigmaY; set { _ekfSigmaY = value; OnPropertyChanged(); } }
        public double EkfBiasAx { get => _ekfBiasAx; set { _ekfBiasAx = value; OnPropertyChanged(); } }
        public double EkfBiasAy { get => _ekfBiasAy; set { _ekfBiasAy = value; OnPropertyChanged(); } }
        public double EkfBiasAlt { get => _ekfBiasAlt; set { _ekfBiasAlt = value; OnPropertyChanged(); } }
        public bool EkfValid { get => _ekfValid; set { _ekfValid = value; OnPropertyChanged(); } }

        public double DhMeasured { get => _dhMeasured; set { _dhMeasured = value; OnPropertyChanged(); } }
        public double DhMap { get => _dhMap; set { _dhMap = value; OnPropertyChanged(); } }
        public double SigmaTotal { get => _sigmaTotal; set { _sigmaTotal = value; OnPropertyChanged(); } }
        public double SigmaTerrainRatio { get => _sigmaTerrainRatio; set { _sigmaTerrainRatio = value; OnPropertyChanged(); } }
        public double LpAccum { get => _lpAccum; set { _lpAccum = value; OnPropertyChanged(); } }

        public double DemOriginX { get => _demOriginX; set { _demOriginX = value; OnPropertyChanged(); } }
        public double DemOriginY { get => _demOriginY; set { _demOriginY = value; OnPropertyChanged(); } }
        public double DemPixelW { get => _demPixelW; set { _demPixelW = value; OnPropertyChanged(); } }
        public double DemPixelH { get => _demPixelH; set { _demPixelH = value; OnPropertyChanged(); } }
        public int DemRasterX { get => _demRasterX; set { _demRasterX = value; OnPropertyChanged(); } }
        public int DemRasterY { get => _demRasterY; set { _demRasterY = value; OnPropertyChanged(); } }

        public int DemThumbW { get => _demThumbW; set { _demThumbW = value; OnPropertyChanged(); } }
        public int DemThumbH { get => _demThumbH; set { _demThumbH = value; OnPropertyChanged(); } }
        public double DemThumbMin { get => _demThumbMin; set { _demThumbMin = value; OnPropertyChanged(); } }
        public double DemThumbMax { get => _demThumbMax; set { _demThumbMax = value; OnPropertyChanged(); } }
        public byte[]? DemThumbData { get => _demThumbData; set { _demThumbData = value; OnPropertyChanged(); } }

        public bool IsConnected { get => _isConnected; set { _isConnected = value; OnPropertyChanged(); } }
        public string StatusText { get => _statusText; set { _statusText = value; OnPropertyChanged(); } }
        public string DebugInfo { get => _debugInfo; set { _debugInfo = value; OnPropertyChanged(); } }

        private double _insX, _insY, _insVx, _insVy, _insHeading, _insAltitude;
        private double _kensX, _kensY, _kensDeltaX, _kensDeltaY;
        private bool _kensValid, _kensFallback, _kensInBounds;
        private double _kensDhError, _kensLp;
        private double _kensSearchWindowHalf, _kensRefBlockSize;
        private double _ekfX, _ekfY, _ekfVx, _ekfVy, _ekfSigmaX, _ekfSigmaY, _ekfBiasAx, _ekfBiasAy, _ekfBiasAlt;
        private bool _ekfValid;
        private double _dhMeasured, _dhMap, _sigmaTotal, _sigmaTerrainRatio, _lpAccum;
        private double _demOriginX, _demOriginY, _demPixelW = 1.0, _demPixelH = -1.0;
        private int _demRasterX, _demRasterY;
        private int _demThumbW, _demThumbH;
        private double _demThumbMin, _demThumbMax;
        private byte[]? _demThumbData;
        private bool _isConnected;
        private string _statusText = "WAITING FOR C++ CORE...";
        private string _debugInfo = "";
        private int _pointCounter;

        public MainViewModel()
        {
            _poller = new TelemetryPoller();
            _poller.DataReceived += OnDataReceived;
            _poller.ConnectionChanged += OnConnectionChanged;
            _poller.Start();
        }

        private void OnConnectionChanged(bool connected)
        {
            Application.Current?.Dispatcher.Invoke(() =>
            {
                IsConnected = connected;
                StatusText = connected ? "CONNECTED" : "WAITING FOR C++ CORE...";
            });
        }

        /// <summary>
        /// Обработчик данных из shared memory.
        /// Вызывается из фонового потока → диспетчеризируем в UI поток.
        /// </summary>
        private void OnDataReceived(SharedMemoryLayout data)
        {
            Application.Current?.Dispatcher.Invoke(() =>
            {
                // Обновление свойств INS
                InsX = data.InsXNorth;
                InsY = data.InsYEast;
                InsVx = data.InsVx;
                InsVy = data.InsVy;
                InsHeading = data.InsHeading;
                InsAltitude = data.InsAltitude;

                // Обновление свойств КЭНС
                KensX = data.KensX;
                KensY = data.KensY;
                KensValid = data.KensValid != 0;

                // Обновление свойств EKF
                EkfX = data.EkfX;
                EkfY = data.EkfY;
                EkfSigmaX = data.EkfSigmaX;
                EkfSigmaY = data.EkfSigmaY;
                EkfValid = data.EkfValid != 0;

                // Обновление метрик рельефа
                DhMeasured = data.DhMeasured;
                DhMap = data.DhMap;
                SigmaTotal = data.SigmaTotal;
                SigmaTerrainRatio = data.SigmaTerrainRatio;
                LpAccum = data.LpAccum;

                IsConnected = true;
                // Добавление точек в траекторию (каждая 3-я точка для экономии)
                _pointCounter++;
                if (_pointCounter % 3 == 0)
                {
                    InsTrajectory.Add(new TrajectoryPoint(data.InsXNorth, data.InsYEast));
                    if (KensValid)
                        KensTrajectory.Add(new TrajectoryPoint(data.KensX, data.KensY));
                    EkfTrajectory.Add(new TrajectoryPoint(data.EkfX, data.EkfY));

                    // Ограничение истории (макс. 2000 точек)
                    if (InsTrajectory.Count > 2000)
                    {
                        InsTrajectory.RemoveAt(0);
                        if (KensTrajectory.Count > 0) KensTrajectory.RemoveAt(0);
                        if (EkfTrajectory.Count > 0) EkfTrajectory.RemoveAt(0);
                    }
                }
            });
        }
        public event PropertyChangedEventHandler? PropertyChanged;
        protected void OnPropertyChanged([CallerMemberName] string? name = null)
            => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(name));

        public void Dispose()
        {
            if (_disposed) return;
            _poller.Dispose();
            _disposed = true;
        }
    }

    public class TrajectoryPoint
    {
        public double North { get; }
        public double East { get; }
        public TrajectoryPoint(double north, double east) { North = north; East = east; }
    }
}