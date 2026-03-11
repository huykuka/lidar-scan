# LiDAR Product Images

This directory contains product images for SICK LiDAR sensors displayed in the sensor node cards.

## Required Images

Add product images for the following models:

- `multiscan.png` - SICK multiScan100 (128x128 or larger)
- `tim_240.png` - SICK TiM240 (128x128 or larger)
- `tim_5xx.png` - SICK TiM5xx series (128x128 or larger)
- `tim_7xx.png` - SICK TiM7xx series (128x128 or larger)
- `tim_7xxs.png` - SICK TiM7xxS series (128x128 or larger)
- `picoscan_120.png` - SICK picoScan120 (128x128 or larger)
- `picoscan_150.png` - SICK picoScan150 (128x128 or larger)

## Image Requirements

- **Format**: PNG or JPG
- **Size**: Minimum 128x128px, recommended 256x256px or larger
- **Aspect Ratio**: Any (will be cropped to fit with `object-cover`)
- **Background**: Transparent or white preferred

## Fallback

If an image is not found, the system falls back to `/lidar-placeholder.svg` (generic LiDAR icon).

## Sources

Product images can be obtained from:
- SICK official website product pages
- Product datasheets (extract images)
- Generate placeholder images with model names if official images unavailable
