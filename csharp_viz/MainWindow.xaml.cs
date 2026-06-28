using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Shapes;
using KensVisualizer.ViewModels;
using Microsoft.Win32;
using KensVisualizer.Services;
using BitMiracle.LibTiff.Classic;
using System.IO;
// using ImageGlider;



namespace KensVisualizer
{
    public partial class MainWindow : Window
    {
        public static MainViewModel _vm;
        private double _scale = 1.0;
        private double _offsetX, _offsetY;
        private bool _hasTransform;
        private WriteableBitmap? _demBitmap;
        private bool _demBitmapApplied;
        private bool _terrainImageLoaded;
        private int _retryCount;
        public string FilePath;

        public MainWindow() { InitializeComponent(); }

        private void Window_Loaded(object sender, RoutedEventArgs e)
        {
            _vm = DataContext as MainViewModel;
        }

        private void PositionMarker(FrameworkElement marker, double east, double north)
        {
            var p = W2S(east, north);
            Canvas.SetLeft(marker, p.X - marker.Width / 2);
            Canvas.SetTop(marker, p.Y - marker.Height / 2);
        }
        private void PositionMarker(Ellipse marker, double x, double y)
        {
            // Устанавливаем позицию маркера на Canvas
            Canvas.SetLeft(marker, x - marker.Width / 2);  // Центрируем по X
            Canvas.SetTop(marker, y - marker.Height / 2);  // Центрируем по Y
            marker.Visibility = Visibility.Visible;
        }


        private void CanvasDraw_SizeChanged(object sender, RoutedEventArgs e)
        {
            double imageWidth = Preview.ActualWidth;
            double imageHeight = Preview.ActualHeight;

            if (imageWidth > 0 && imageHeight > 0)
            {
                DrawingCanvas.Width = imageWidth;
                DrawingCanvas.Height = imageHeight;
            }
        }
        private void Preview_SizeChanged(object sender, RoutedEventArgs e)
        {
            if (Preview.Source != null)
            {
                // Получаем фактические размеры Image после масштабирования
                double imageWidth = MapCanvas.ActualWidth;
                double imageHeight = MapCanvas.ActualHeight;

                if (imageWidth > 0 && imageHeight > 0)
                {
                    Preview.Width = imageWidth;
                    Preview.Height = imageHeight;
                }
            }
        }
        private void LoadImageTiff_Click(object sender, RoutedEventArgs e)
        {
            var openFileDialog = new OpenFileDialog
            {
                Title = "Выберите изображение",
                Filter = "Images|*.tif;*.tiff"
            };

            if (openFileDialog.ShowDialog() == true)
            {
                FilePath = openFileDialog.FileName;
                LoadAndSaveTiffToBmp();
            }
        }
        private void LoadImageBmp_Click(object sender, RoutedEventArgs e)
        {
            var openFileDialog = new OpenFileDialog
            {
                Title = "Выберите изображение",
                Filter = "Images|*.bmp;"
            };

            if (openFileDialog.ShowDialog() == true)
            {
                FilePath = openFileDialog.FileName;
                LoadBmp();
            }
        }
        private void LoadBmp()
        {
            try
            {
                var bmp = new BitmapImage();
                bmp.BeginInit();
                bmp.UriSource = new Uri(System.IO.Path.GetFullPath(FilePath), UriKind.Absolute);
                bmp.CacheOption = BitmapCacheOption.OnLoad;
                bmp.EndInit();
                bmp.Freeze();
                Preview.Source = bmp;
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Ошибка загрузки: {ex.Message}");
            }
        }
        private void LoadAndSaveTiffToBmp()
        {
            if (!System.IO.File.Exists(FilePath)) return;

            try
            {
                // using (var tiffImage = Image.File(FilePath))
                // {
                //     tiffImage.Save("output.bmp", ImageFormat.Bmp);
                // }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"Ошибка: {ex.Message}");
            }
        }
        // private void ConvertTiffToBmp(string tiffPath, string bmpPath)
        // {
        //     using var input = File.OpenRead(tiffPath);
        //     var decoder = new TiffBitmapDecoder(input, BitmapCreateOptions.PreservePixelFormat, BitmapCacheOption.OnLoad);
        //     using var output = File.Create(bmpPath);
        //     var encoder = new BmpBitmapEncoder();
        //     foreach (var frame in decoder.Frames)
        //         encoder.Frames.Add(frame);
        //     encoder.Save(output);
        // }
        private void ParseNmea_Click(object sender, RoutedEventArgs e)
        {
            try
            {
                var gga = ParseGpgga(nmeaBox.Text);
                resultBox.Text =
                    $"Talker: {gga.Talker}\n" +
                    $"Time UTC: {gga.UtcTime:hh\\:mm\\:ss}\n" +
                    $"Latitude: {gga.Latitude:F6}\n" +
                    $"Longitude: {gga.Longitude:F6}\n" +
                    $"Fix quality: {gga.FixQuality}\n" +
                    $"Satellites: {gga.Satellites}\n" +
                    $"HDOP: {gga.Hdop}\n" +
                    $"Altitude: {gga.Altitude} {gga.AltitudeUnit}\n" +
                    $"Geoid separation: {gga.GeoidSeparation} {gga.GeoidUnit}\n" +
                    $"Checksum valid: {gga.ChecksumValid}";
                var p = GeoTiffHelper.GeoToPixel(Tiff.Open(FilePath, "r"), gga.Longitude, gga.Latitude);
                Point target = new Point(20.0, 20.0);
                DrawPoint(target);
            }
            catch (Exception ex)
            {
                resultBox.Text = ex.Message;
            }
        }
        public void DrawPoint(Point target)
        {
            var dot = new Ellipse
            {
                Width = 8,
                Height = 8,
                Fill = Brushes.Red,
                Stroke = Brushes.White,
                StrokeThickness = 1
            };
            Canvas.SetLeft(dot, target.X - dot.Width / 2);
            Canvas.SetTop(dot, target.Y - dot.Height / 2);
            DrawingCanvas.Children.Add(dot);
        }
        private static GpggaData ParseGpgga(string sentence)
        {
            if (string.IsNullOrWhiteSpace(sentence))
                throw new ArgumentException("Пустая строка NMEA.");

            sentence = sentence.Trim();

            if (!sentence.StartsWith("$"))
                throw new ArgumentException("Строка должна начинаться с $.");

            var star = sentence.IndexOf('*');
            if (star < 0)
                throw new ArgumentException("Нет контрольной суммы *XX.");

            var dataPart = sentence.Substring(1, star - 1);
            var checksumText = sentence.Substring(star + 1);

            byte checksum = 0;
            foreach (char c in dataPart)
                checksum ^= (byte)c;

            bool checksumValid = byte.TryParse(checksumText, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out var expected)
                                 && expected == checksum;

            var parts = dataPart.Split(',');

            if (parts.Length < 15)
                throw new ArgumentException("Недостаточно полей GPGGA.");

            if (!parts[0].EndsWith("GGA", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Это не GPGGA строка.");

            var talker = parts[0].Substring(0, Math.Max(0, parts[0].Length - 3));
            var utc = ParseUtc(parts[1]);
            var lat = ParseCoord(parts[2], parts[3], true);
            var lon = ParseCoord(parts[4], parts[5], false);
            var fixQuality = int.TryParse(parts[6], out var fq) ? fq : -1;
            var satellites = int.TryParse(parts[7], out var sat) ? sat : -1;
            var hdop = ParseDouble(parts[8]);
            var altitude = ParseDouble(parts[9]);
            var altitudeUnit = parts[10];
            var geoidSeparation = ParseDouble(parts[11]);
            var geoidUnit = parts[12];

            return new GpggaData
            {
                Talker = talker,
                UtcTime = utc,
                Latitude = lat,
                Longitude = lon,
                FixQuality = fixQuality,
                Satellites = satellites,
                Hdop = hdop,
                Altitude = altitude,
                AltitudeUnit = altitudeUnit,
                GeoidSeparation = geoidSeparation,
                GeoidUnit = geoidUnit,
                ChecksumValid = checksumValid
            };
        }
        private static TimeSpan ParseUtc(string value)
        {
            if (string.IsNullOrWhiteSpace(value) || value.Length < 6)
                return TimeSpan.Zero;

            int hh = int.Parse(value.Substring(0, 2));
            int mm = int.Parse(value.Substring(2, 2));
            int ss = int.Parse(value.Substring(4, 2));
            return new TimeSpan(hh, mm, ss);
        }

        private static double ParseCoord(string value, string hemisphere, bool isLatitude)
        {
            if (string.IsNullOrWhiteSpace(value))
                return double.NaN;

            double raw = double.Parse(value, CultureInfo.InvariantCulture);
            int degDigits = isLatitude ? 2 : 3;

            double degrees = Math.Floor(raw / Math.Pow(10, value.Length - degDigits));
            double minutes = raw - degrees * Math.Pow(10, value.Length - degDigits);
            double result = degrees + minutes / 60.0;

            if (hemisphere.Equals("S", StringComparison.OrdinalIgnoreCase) ||
                hemisphere.Equals("W", StringComparison.OrdinalIgnoreCase))
                result = -result;

            return result;
        }

        private static double ParseDouble(string value)
        {
            return double.TryParse(value, System.Globalization.NumberStyles.Float, CultureInfo.InvariantCulture, out var d)
                ? d
                : double.NaN;
        }
        public class GpggaData
        {
            public string Talker { get; set; }
            public TimeSpan UtcTime { get; set; }
            public double Latitude { get; set; }
            public double Longitude { get; set; }
            public int FixQuality { get; set; }
            public int Satellites { get; set; }
            public double Hdop { get; set; }
            public double Altitude { get; set; }
            public string AltitudeUnit { get; set; }
            public double GeoidSeparation { get; set; }
            public string GeoidUnit { get; set; }
            public bool ChecksumValid { get; set; }
        }
        private Point W2S(double east, double north)
        {
            if (_vm == null) return new Point(0, 0);
            double col = (east - _vm.DemOriginX) / Math.Abs(_vm.DemPixelW);
            double row = (north - _vm.DemOriginY) / _vm.DemPixelH;
            return new Point(col * _scale + _offsetX, row * _scale + _offsetY);
        }
    }
}