using System;
using System.Runtime.InteropServices;

namespace KensVisualizer.Models
{
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    public struct SharedMemoryLayout
    {
        public uint Magic;
        public uint Version;
        public ulong TimestampUs;

        public double InsXNorth;
        public double InsYEast;
        public double InsVx;
        public double InsVy;
        public double InsHeading;
        public double InsAltitude;

        public double KensX;
        public double KensY;
        public double KensDeltaX;
        public double KensDeltaY;
        public byte KensValid;

        public double EkfX;
        public double EkfY;
        public double EkfVx;
        public double EkfVy;
        public double EkfBiasAx;
        public double EkfBiasAy;
        public double EkfBiasAlt;
        public double EkfSigmaX;
        public double EkfSigmaY;
        public byte EkfValid;

        public double DhMeasured;
        public double DhMap;
        public double SigmaTotal;
        public double SigmaTerrainRatio;
        public double LpAccum;

        public double DemOriginX;
        public double DemOriginY;
        public double DemPixelW;
        public double DemPixelH;
        public int DemRasterX;
        public int DemRasterY;

        public int DemThumbW;
        public int DemThumbH;
        public double DemThumbMin;
        public double DemThumbMax;

        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 65536)]
        public byte[] DemThumbData;

        public byte KensInBounds;
        public byte KensFallback;
        public byte KensValidityFlags;
        public double KensSearchWindowHalf;
        public double KensRefBlockSize;
        public double KensDhError;
        public double KensLp;

        public const uint MAGIC_VALUE = 0x4B454E53;
        public bool IsValid => Magic == MAGIC_VALUE;
    }
}