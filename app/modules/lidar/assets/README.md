# LiDAR Device Thumbnails

This directory contains thumbnail images for SICK LiDAR device models.

## Structure

- **placeholder.png**: Base placeholder for all devices (145 bytes minimal PNG)
- **{model_id}.png**: Specific thumbnail for each SICK device model

## Image Requirements

- **Format**: PNG
- **Size**: Recommended 200x150px (or similar aspect ratio)
- **Quality**: High-quality product photos showing the physical device
- **Background**: Transparent or white background preferred

## Supported Models (24 Enabled + 1 Disabled)

The following device models need thumbnail images:

### multiScan Series
- multiscan.png - SICK multiScan100

### TiM Series  
- tim240.png - SICK TiM240 (Prototype)
- tim5xx.png - SICK TiM5xx Family
- tim7xx.png - SICK TiM7xx Family (Non-Safety) 
- tim7xxs.png - SICK TiM7xxS Family (Safety Device)

### LMS Series
- lms1xx.png - SICK LMS1xx Family
- lms1xxx.png - SICK LMS1104 (Firmware 1.x)
- lms1xxx_v2.png - SICK LMS1104 (Firmware 2.x)
- lms5xx.png - SICK LMS5xx Family
- lms4xxx.png - SICK LMS4000 Family

### MRS Series
- mrs1xxx.png - SICK MRS1104
- mrs6xxx.png - SICK MRS6124

### LRS Series
- lrs4xxx.png - SICK LRS4000
- lrs36x0.png - SICK LRS36x0
- lrs36x1.png - SICK LRS36x1

### LD-MRS Series (**DISABLED**)
- ldmrs.png - SICK LD-MRS Family *(Hidden from frontend dropdown)*

### OEM Series
- oem15xx.png - SICK LD-OEM15xx

### NAV Series
- nav2xx.png - SICK NAV210/NAV245
- nav31x.png - SICK NAV310
- nav350.png - SICK NAV350

### RMS Series
- rms.png - SICK RMS1009/RMS2000

### picoScan Series
- picoscan120.png - SICK picoScan120
- picoscan150.png - SICK picoScan150

## Model Availability

- **Frontend Dropdown**: Shows 24 enabled models (excludes LD-MRS)
- **Backend Validation**: Supports all 25 models (includes LD-MRS for existing configs)
- **Assets Storage**: All 25 thumbnails stored (including disabled models)

## API Integration

These images are served via the REST API endpoint:
```
GET /api/v1/assets/lidar/{filename}
```

Example: `/api/v1/assets/lidar/multiscan.png`