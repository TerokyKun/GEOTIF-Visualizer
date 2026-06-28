using BitMiracle.LibTiff.Classic;
using System;
using System.Globalization;
namespace KensVisualizer.Services
{
    public class GeoTiffHelper
    {
        public static (double lon, double lat) ParseGpgga(string sentence)
        {
            var s = sentence.Trim();
            if (s.StartsWith("$")) s = s[1..];
            var star = s.IndexOf('*');
            if (star >= 0) s = s.Substring(0, star);

            var p = s.Split(',');
            if (p.Length < 6 || !p[0].EndsWith("GGA", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Not GPGGA");
            return (
                ParseCoord(p[4], p[5], false),
                ParseCoord(p[2], p[3], true)
            );
        }

        public static (double x, double y) GeoToPixel(Tiff tiff, double lon, double lat)
        {
            var scale = tiff.GetField((TiffTag)33550);
            var tie = tiff.GetField((TiffTag)33922);

            if (scale == null || tie == null)
                throw new InvalidOperationException("GeoTIFF tags not found");

            byte[] scaleBytes = scale[1].GetBytes();
            byte[] tieBytes = tie[1].GetBytes();

            double pixelSizeX = BitConverter.ToDouble(scaleBytes, 0);
            double pixelSizeY = BitConverter.ToDouble(scaleBytes, 8);

            double tiePixelX = BitConverter.ToDouble(tieBytes, 0);
            double tiePixelY = BitConverter.ToDouble(tieBytes, 8);
            double tieLon = BitConverter.ToDouble(tieBytes, 24);
            double tieLat = BitConverter.ToDouble(tieBytes, 32);

            double x = tiePixelX + (lon - tieLon) / pixelSizeX;
            double y = tiePixelY + (tieLat - lat) / pixelSizeY;

            return (x, y);
        }

        public static PointD GetTargetPoint(string tiffPath, string gpgga)
        {
            var gps = ParseGpgga(gpgga);

            using var tiff = Tiff.Open(tiffPath, "r");
            if (tiff == null)
                throw new InvalidOperationException("Cannot open TIFF");

            var p = GeoToPixel(tiff, gps.lon, gps.lat);
            return new PointD(p.x, p.y);
        }

        private static double ParseCoord(string value, string hemi, bool lat)
        {
            double raw = double.Parse(value, CultureInfo.InvariantCulture);
            int degDigits = lat ? 2 : 3;

            double deg = double.Parse(value.Substring(0, degDigits), CultureInfo.InvariantCulture);
            double min = double.Parse(value.Substring(degDigits), CultureInfo.InvariantCulture);
            double dec = deg + min / 60.0;

            if (hemi.Equals("S", StringComparison.OrdinalIgnoreCase) ||
                hemi.Equals("W", StringComparison.OrdinalIgnoreCase))
                dec = -dec;

            return dec;
        }
    }

    public readonly struct PointD
    {
        public readonly double X;
        public readonly double Y;
        public PointD(double x, double y) { X = x; Y = y; }
    }
}