# PROJECT HANDOFF FOR CHATGPT: EGYPTIAN HERITAGE AI AND AUGMENTED REALITY PLATFORM

**Target Audience:** AI Assistant / ChatGPT / Lead AR Engineer  
**Project Name:** Heritage Explorer / Egyptian Cultural Heritage AI and AR Social Platform  
**Root Locations:**  
- Primary App Codebase: `D:\Gradautaion_Project\Integrated_App`  
- Research and Documentation: `D:\Gradautaion_Project\Papers`, `D:\Gradautaion_Project\Power_Points`  
**Handoff Date:** October 2026  
**Document Status:** Persistent Technical Context and Architectural Blueprint  

---

## 1. Project Purpose and Objectives

### 1.1 Academic and Technical Vision
This project develops an **AI-powered Augmented Reality (AR) and location-aware social platform** dedicated to Egyptian cultural heritage (archaeological sites, monuments, museum artifacts, and ancient jewelry).

The system integrates:
1. **Real-Time On-Device / Cloud Hybrid Computer Vision:** Real-time detection and instance segmentation of archaeological landmarks and museum artifacts using fine-tuned YOLO models, FastSAM instance segmentation, and zero-shot fallback via Gemini Multimodal Vision API.
2. **Active Learning and Dataset Expansion Pipeline:** Human-in-the-loop candidate harvesting mechanism (`/api/confirm`, `/api/reject`, `/api/prepare_dataset`) that collects novel landmarks, computes image hashes to prevent duplicate submissions, and packages data for retraining.
3. **Location-Based Proximity and Social Layer:** Real-time geohash clustering and haversine calculations matching visitor GPS coordinates to registered heritage sites, serving site-specific community feeds, crowd posts, and historical trivia via Socket.IO live events.
4. **Augmented Reality (AR) Overlay (The Next Milestone):** Rendering contextually anchored, orientation-stabilized labels, 3D overlays, architectural historical reconstructions, and interactive museum artifacts directly in the visitor camera stream.

---

## 2. Architecture and Technology Stack

### 2.1 Technology Stack Matrix
| Layer | Technologies and Frameworks | Version / Details | Purpose |
|---|---|---|---|
| **Backend Framework** | Flask, Flask-CORS, Flask-SocketIO | Flask >= 3.0.0, SocketIO >= 5.3.0 | API server, background async job management, WebSockets |
| **Concurrency / Worker** | eventlet, gunicorn | eventlet >= 0.35.0, gunicorn 21.2.0 | Async SocketIO event loop and concurrency on production / local |
| **Computer Vision and Deep Learning** | Ultralytics YOLOv11 (`yolo11n.pt`), FastSAM (`FastSAM-s.pt`), OpenCV Headless, Pillow, NumPy | Ultralytics >= 8.0.0, OpenCV >= 4.8.0, NumPy >= 1.26.0 | Object detection, visual instance segmentation, polygon contour extraction |
| **Multimodal Vision Fallback** | Google Generative AI (`google-generativeai`), Gemini REST API | `google-generativeai` >= 0.8.0, REST v1beta fallback | Zero-shot identification of unidentified monuments with GPS auto-extraction |
| **Database** | MongoDB Atlas (`heritage_social` cluster), PyMongo | PyMongo >= 4.6.0, dnspython >= 2.5.0 | Geo-indexed objects, locations, social posts, training candidates |
| **Frontend UI** | HTML5, Vanilla JavaScript (ES6+), CSS3 Custom Variables | Responsive Glassmorphic Dark UI | Dual-mode interface: Landmark Detection and Museum Artifact Segmentation |
| **Mapping and Location** | Leaflet.js (v1.9.4 CDN), Custom Pure-Python Geohash | OpenStreetMap tiles, 6-character Geohashes | Interactive heritage map, proximity radius visualization, GPS simulator |
| **AR Prototype Engine** | DeviceOrientationEvent, DeviceMotionEvent, WebRTC `getUserMedia` | HTML5 Device Sensors API | Orientation-stabilized 3D-perspective artifact badge overlay |
| **Cloud Deployment** | Railway / Nixpacks | `railway.json`, `nixpacks.toml`, `Procfile` | Production container configuration with system dependencies |

### 2.2 Directory and File Structure
```text
D:\Gradautaion_Project\
├── Integrated_App\
│   ├── Database\                                  # Initial Mongo JSON seed exports
│   │   ├── heritage_social.locations.json         # Known heritage sites (Giza Pyramids, Egyptian Museum)
│   │   ├── heritage_social.objects.json           # Specific monuments and artifacts (Khafre, Tutankhamun Mask)
│   │   ├── heritage_social.posts.json             # Heritage social commentary and historical facts
│   │   └── heritage_social.training_candidates.json
│   ├── egypt-landmarks-3-classes\                 # Base landmark dataset (train/val/test + data.yaml)
│   ├── expanded_dataset\                          # Active learning expanded dataset for YOLO retraining
│   ├── models\                                    # Model weights directory
│   │   ├── FastSAM-s.pt                           # 23.8 MB - Instance segmentation for museum jewelry
│   │   ├── yolo11n.pt                             # 5.6 MB - Base / custom YOLOv11 weights
│   │   ├── yolov8n.pt                             # 6.5 MB - YOLOv8 nano model
│   │   ├── yolov8s-world.pt                       # 27.1 MB - Open-vocabulary YOLO-World
│   │   └── yolov8_best.pt                         # 6.2 MB - Historical custom-trained weights
│   ├── outputs\                                   # Artifact pipeline output storage
│   │   ├── detection.jpg                          # Last pipeline detection overlay
│   │   ├── segmentation.jpg                       # Last pipeline color instance mask overlay
│   │   ├── results.json                           # Extracted items, classes, bboxes, crops
│   │   └── objects\                               # Segmented transparent PNG crops (Item_01.png, etc.)
│   ├── pending_dataset\                           # Candidate data staging for active learning
│   │   ├── class_mapping.json                     # Class-to-ID mapping dictionary
│   │   ├── rejection_log.json                     # Log of false positives rejected by users
│   │   └── <Class-Name>\                          # Subdirectories per class with images/, labels/, metadata/
│   ├── runs\                                      # Colab training execution records
│   ├── templates\
│   │   └── index.html                             # 193 KB - Complete glassmorphic Web App frontend
│   ├── temp_uploads\                              # Temporary image cache during hashing / verification
│   ├── uploads\
│   │   └── candidates\                            # Staged images for verification review dashboard
│   ├── .env / atlas-credentials.env               # MongoDB connection string and GEMINI_API_KEY
│   ├── app.py                                     # 105 KB - Core Flask + SocketIO application server
│   ├── artifact_segmentation_pipeline.py          # 23 KB - FastSAM museum artifact and jewelry pipeline
│   ├── nixpacks.toml                              # Railway Nixpacks build definition
│   ├── Procfile                                   # Railway worker process command
│   ├── railway.json                               # Railway deployment configurations
│   ├── requirements.txt                           # Python pip dependencies
│   ├── run_app.bat                                # Windows startup script
│   ├── test_museum_jewelry.jpg                    # Sample image with 3 gold pendants/necklaces
│   └── upload_db.py                               # DB seed migration script
├── Papers\                                        # Published/submitted IEEE conference papers
└── Power_Points\                                  # Graduation defense presentation decks
```

---

## 3. AI Models and Artifact Recognition Pipeline

### 3.1 Overview of Implemented Models
The codebase implements a multi-stage **hybrid inference architecture**:

1. **YOLOv11 (`models/yolo11n.pt` / `models/yolo11_best.pt`):**
   - **Primary Duty:** Landmark detection and bounding box extraction.
   - **Supported Built-in Classes:** `Khafre-Pyramid`, `Mask-of-Tutankhamun`, `Sphinx`, `Great-Pyramid`.
   - **Confidence Threshold:** `0.60`.
   - **Optimization:** To prevent high RAM usage on 1GB instances (e.g. Railway), `get_yolo_v8()` aliases directly to `get_yolo_y11()` lazy singleton, avoiding duplicate model weights in memory.

2. **FastSAM-s (`models/FastSAM-s.pt`):**
   - **Primary Duty:** Museum artifact and jewelry instance segmentation (`artifact_segmentation_pipeline.py`).
   - **Features:** Detects multiple overlapping or small items (e.g. gold pendants, beads, amulets), isolates foreground masks, extracts transparent RGBA PNG crops, and computes spatial bounding boxes.
   - **Confidence Threshold:** `0.20`.
   - **CPU / Threading Safeguard:** OpenMP/MKL forced to `torch.set_num_threads(1)` to prevent eventlet worker lockups.
   - **Adaptive Fallback:** If FastSAM fails or weights are absent, it falls back to morphological edge/Otsu threshold contour segmentation.

3. **YOLO-World (`models/yolov8s-world.pt`):**
   - **Primary Duty:** Open-vocabulary prompt-guided object detection for custom user-confirmed classes in `pending_dataset/`.
   - **Threshold:** `0.35`.
   - *Note on status:* In `app.py`, `get_yolo_world()` is toggled to return `None` in memory-constrained environments, with inline logic safely checking before inference.

4. **Google Gemini Multimodal Vision API (Zero-Shot Fallback):**
   - **Primary Duty:** Universal fallback when YOLO yields no detections above threshold.
   - **Models Used:** Direct REST endpoint cascading across `gemini-2.5-flash`, `gemini-3.5-flash`, `gemini-flash-latest`, and SDK `gemini-1.5-flash-latest`.
   - **Context-Aware Prompting:** Injects the user GPS coordinates and names of known nearby landmarks within the prompt to bias the model towards accurate Egyptian heritage site identification.
   - **Structured JSON Output:** Returns `possibleLandmark`, `description`, `confidence` (0-100), `isNewLandmark` (boolean), `reason`, and estimated real-world `latitude`/`longitude`.

### 3.2 Visual Segmentation Overlay Generator (`generate_visual_segmentation()`)
Located in `app.py` (lines 1140-1280):
- Takes raw bounding box coordinates and optional YOLO mask.
- If instance mask is absent, applies Otsu thresholding + Canny edge detection + bilateral filtering inside the ROI to compute a contour hull.
- Generates a translucent alpha-blended polygon overlay (45% opacity).
- Renders a multi-layer glowing neon perimeter contour and AR corner brackets.
- Adds an AR glassmorphic pill showing class name, confidence, and `[MASK]` tag.
- Returns normalized polygon vertices `[[x_norm, y_norm], ...]` suitable for AR projection.

### 3.3 End-to-End Recognition Workflow
```
[User Camera / Upload]
         │
         ▼
  [Compute MD5 Hash]
         │
    Duplicate? ────► Return Cached Detection & Object Data
         │ No
         ▼
[YOLOv11 Detection (conf >= 0.60)]
         │
    Detected? ────► [MongoDB Object Match] ──► [Neon Segmentation Overlay] ──► [Return AR Payload]
         │ No
         ▼
[Check Custom Pending Classes]
         │
    Matched?  ────► [Auto-Register Landmark] ──► [Return AR Payload]
         │ No
         ▼
[Gemini Vision Zero-Shot Fallback]
         │
  Extract Landmark, GPS, Description
         │
    Already in DB? ──► [Auto-Confirm: Save Sample to Pending Dataset] ──► [Return AR Payload]
         │ No
         ▼
  [Stage Candidate in uploads/candidates/ & Show Curator Review UI]
```

---

## 4. Existing Application Features and Implementation Status

| Feature | Implementation Location | Description | Status |
|---|---|---|---|
| **Landmark Detection** | `app.py:1103 (/api/detect)` | Multi-stage recognition (YOLOv11 -> Custom -> Gemini Zero-Shot). Asynchronous worker thread with polling endpoint `/api/detect/result/<job_id>`. | **Fully Functional** |
| **Museum Artifact Segmentation** | `artifact_segmentation_pipeline.py`, `app.py:877 (/api/artifacts/segment)` | FastSAM-powered instance segmentation for museum cases; crops transparent PNGs of individual jewelry pieces into `/outputs/objects/`. | **Fully Functional** |
| **Active Learning and Feedback** | `app.py:1823 (/api/confirm)`, `1899 (/api/reject)` | Allows user or curator to approve or reject Gemini identifications. Generates YOLO-formatted labels in `pending_dataset/<class>/`. | **Fully Functional** |
| **Dataset Packaging** | `app.py:2168 (/api/prepare_dataset)` | Compiles pending staged data into `expanded_dataset/` with updated `data.yaml` ready for YOLO fine-tuning. | **Fully Functional** |
| **Interactive Heritage Map** | `templates/index.html` (Leaflet.js) | Displays user location marker, nearby heritage sites, and geofence proximity zones (e.g. 80m radius). | **Fully Functional** |
| **GPS Simulator** | `app.py:2003 (/api/simulate/move)`, `templates/index.html` | Allows quick switching between simulated tourist locations (Giza Pyramids, Egyptian Museum, Out of Range). | **Fully Functional** |
| **Location-Based Social Feed** | `app.py:945 (/api/posts)`, `1060 (/api/nearby)` | Fetches posts tied to nearby monuments. Emits real-time `new_post` and `object_registered` events via SocketIO. | **Fully Functional** |
| **Live Web Camera Capture** | `templates/index.html:450+` | HTML5 video stream with capture canvas, rear-camera prioritization (`facingMode: environment`). | **Fully Functional** |
| **Orientation-Stabilized AR Prototype** | `templates/index.html:500-750, 3588-3750` | Fullscreen camera view rendering an orientation-stabilized badge using device gyroscope (`DeviceOrientationEvent`). | **Working Prototype / Baseline** |
| **Accelerometer Diagnostics** | `templates/index.html:3450-3585` | Mobile sensor diagnostic panel verifying accelerometer (X/Y/Z) and gyroscope stream validity. | **Fully Functional** |

---

## 5. Backend, Database and API Specifications

### 5.1 MongoDB Collections Schema
The application uses the `heritage_social` database (with built-in offline mock collection fallback if Atlas is unreachable).

1. **`locations` Collection:**
   ```json
   {
     "_id": "ObjectId(...)",
     "location_id": "L001",
     "name": "Giza Pyramids",
     "latitude": 29.9792,
     "longitude": 31.1342,
     "geohash": "stq4s3"
   }
   ```

2. **`objects` Collection:**
   ```json
   {
     "_id": "ObjectId(...)",
     "object_id": "O001",
     "name": "Khafre Pyramid",
     "class_name": "Khafre-Pyramid",
     "location_id": "L001",
     "latitude": 29.9761,
     "longitude": 31.1308,
     "geohash": "stq4s2",
     "radius_m": 80
   }
   ```

3. **`posts` Collection:**
   ```json
   {
     "_id": "ObjectId(...)",
     "post_id": "P001",
     "location_id": "L001",
     "object_id": "O001",
     "content": "The Khafre Pyramid stands 136 meters tall!",
     "author": "Heritage Explorer",
     "createdAt": "2026-08-30T10:00:00Z"
   }
   ```

4. **`training_candidates` Collection:**
   ```json
   {
     "_id": "ObjectId(...)",
     "imagePath": "uploads/candidates/uuid.jpg",
     "description": "Visual description...",
     "suggestedLandmark": "Tomb of Perneb",
     "isNewLandmark": true,
     "confidence": 88,
     "reason": "Architectural mastaba structure",
     "latitude": 29.8712,
     "longitude": 31.2165,
     "status": "pending",
     "autoConfirmed": false,
     "createdAt": "2026-10-04T12:00:00Z"
   }
   ```

### 5.2 Key REST Endpoints and Socket Events
- `POST /api/detect` or `/api/predict`: Form-data with `image`, `lat`, `lng`, `model_type` (`v11`). Returns `{"job_id": "...", "status": "pending"}`.
- `GET /api/detect/result/<job_id>`: Polling endpoint returning detection boxes, polygon segmentation contours, matched MongoDB object, and posts.
- `POST /api/artifacts/segment`: Processes museum artifacts/jewelry using FastSAM, returning individual transparent PNG crops and bounding boxes.
- `GET /api/nearby?lat=...&lng=...`: Returns heritage locations and objects within proximity geohashes.
- `POST /api/posts`: Adds a user post tied to an `object_id` and emits `new_post` via WebSockets.
- `POST /api/confirm`: Approves a Gemini candidate, saves YOLO labels to `pending_dataset/`, and registers new object in MongoDB.
- `POST /api/reject`: Rejects candidate, appending to `pending_dataset/rejection_log.json`.
- `POST /api/simulate/move`: Updates mock visitor coordinates to test geofencing.
- **WebSocket Events:**
  - `new_post`: Broadcasts community posts in real-time.
  - `object_registered`: Broadcasts when a novel landmark is discovered and registered.
  - `object_changed`: Broadcasts location/geofence updates.

---

## 6. Preparation for Augmented Reality (AR) Implementation

### 6.1 Application Nature and Framework Analysis
The application is currently an **optimized, mobile-responsive Web Application (Progressive Web Application / WebAR)** running on modern mobile browsers (Safari on iOS, Chrome on Android).
- It is **not** currently packaged in a native wrapper (such as React Native, Flutter, Swift ARKit, or Kotlin ARCore).
- It runs inside standard mobile browsers via HTTPS using standard HTML5 APIs (`navigator.mediaDevices.getUserMedia`, `DeviceOrientationEvent`, `DeviceMotionEvent`).

### 6.2 Compatible AR Technologies
Given the current Web stack, there are three primary paths for AR implementation:

1. **Path A: Pure WebAR via WebXR Device API (Recommended for modern Android Chrome):**
   - Direct standard for SLAM (Simultaneous Localization and Mapping), plane detection, and hit-testing in the browser without third-party plugins.
2. **Path B: Computer Vision WebAR via Three.js + MindAR.js or AR.js (Recommended Cross-Platform for Mobile Web):**
   - **Image-Target AR (MindAR.js / AR.js):** Tracks 2D archaeological markers, informational plaques, museum displays, or postcard images.
   - **Compatible with both iOS Safari and Android Chrome.**
   - Seamlessly integrates with Three.js to render 3D GLTF models, interactive labels, and floating informative billboards over artifacts.
3. **Path C: Sensor-Fused Spatial Tracking (Upgrading Current `ARSession`):**
   - Extends the existing device-orientation matrix with optical flow (e.g., using OpenCV.js or Lucas-Kanade feature point tracking on the camera feed) to approximate translation without requiring full WebXR support on iOS.
4. **Path D: Cross-Platform Mobile Native Wrapper (Capacitor / Flutter / React Native):**
   - If native ARKit (iOS) and ARCore (Android) are strictly mandated for 3D object scanning (e.g. ARCore Geospatial API for outdoor pyramids), the existing Flask backend serves as the REST/WebSocket API, while wrapping the frontend in Capacitor or building a companion mobile client.

### 6.3 Connecting AI Recognition to the AR Experience
**CRITICAL TECHNICAL DISTINCTION:**  
*Recognition is NOT tracking.*
- **What YOLO and FastSAM provide:** Frame-by-frame 2D bounding boxes `[x1, y1, x2, y2]`, class labels, confidence scores, and 2D pixel-level polygon masks `[[x_norm, y_norm], ...]`.
- **What is missing for true AR:** A 6-DOF (Degrees of Freedom: X, Y, Z translation + Pitch, Yaw, Roll rotation) pose matrix that anchors a virtual object to a specific physical coordinate in 3D space when the camera moves.

#### The AI-to-AR Connection Pipeline:
1. **Trigger Phase (Recognition):** The user points the camera at an artifact (e.g., King Tutankhamun Mask or jewelry pendant). The backend returns the classification and normalized 2D bounding box/polygon.
2. **Anchor Initialization:** The AR subsystem takes the 2D bounding box center and raycasts into the 3D scene (using WebXR hit-testing, a predefined 3D anchor, or an Image Target feature map corresponding to the detected class).
3. **Continuous Tracking:** Once initialized, the AR tracking engine (Three.js + WebXR / MindAR) maintains the 6-DOF pose of the anchor at 60 FPS locally on the device without continuously calling the backend AI server.
4. **Interactive AR Overlay:** A floating 3D label, historical audio guide button, or 3D digital twin (GLTF) renders pinned to the artifact.

### 6.4 Tracking Method Suitability Matrix
| Tracking Method | Suitability for this Project | Why / Why Not? |
|---|---|---|
| **Image-Target Tracking (MindAR / AR.js)** | **Highest for Museum Artifacts and Plaques** | Museum exhibits feature informational signs, photos, and high-contrast relief carvings that make ideal 2D planar tracking targets. |
| **Surface / World Plane Tracking (WebXR SLAM)** | **High for General Outdoor and Indoor Placing** | Allows placing full-scale 3D models of pyramids or statues on floors/tables. Requires Android Chrome WebXR or WebXR Viewer on iOS. |
| **Object / 3D CAD Tracking** | **Medium (Complex in Web)** | Tracking full 3D statues from any angle requires feature-point point clouds or native ARKit/ARCore object scanning. |
| **Sensor-Fused Orientation Tracking (Current Baseline)** | **Implemented Baseline** | Already works on all mobile phones without extra libraries, but only locks orientation (heading/tilt), not 3D spatial depth. |

### 6.5 Smallest Working AR Milestone (Milestone 1)
**Interactive Three.js AR Billboard and 3D Viewer Anchored to Detected Artifact**
1. When `/api/detect` or `/api/artifacts/segment` identifies an artifact (e.g., King Tut Mask or a pendant):
2. Load an interactive **Three.js** canvas overlay atop the camera stream (`#ar-scene`).
3. Anchor a 3D glassmorphic historical card (with artifact name, dynasty, material, and community post count) positioned at the normalized bounding box center.
4. Allow the user to tap the card to expand a 3D GLTF preview of the artifact (or a rotating holographic Egyptian relic icon) rendered with realistic lighting.
5. Provide a toggle to switch between Sensor-Stabilized Mode and MindAR/WebXR Surface Tracking.

### 6.6 Files to Modify and New Files Needed for AR
- **Files to Modify:**
  - `templates/index.html`:
    - Add Three.js (`three.min.js`) and GLTFLoader CDN scripts in `<head>`.
    - Upgrade the existing `ARSession` JavaScript module (lines 3588-3750) to instantiate a Three.js scene, camera, and renderer mapped to `#ar-video`.
    - Connect the detection result bounding box coordinates `result.detections[0]` and `result.segmentation.polygons` directly into the Three.js viewport projection.
  - `app.py`:
    - Add a static route or endpoint to serve 3D models (e.g. `/models/3d/<filename>.glb` or `/static/models/`).
    - Add `model_3d_url` field to MongoDB `objects` schema to link recognized artifacts to their corresponding 3D GLTF assets.
- **New Files to Create:**
  - `static/models/`: Directory storing sample 3D Egyptian heritage assets (GLB format, e.g. `tut_mask.glb`, `pyramid.glb`, `scarab.glb`).
  - `static/js/ar_controller.js` (Optional clean refactor): Extracted AR engine separating Three.js rendering and sensor handling from `index.html`.

---

## 7. Current Development Status and Verified Facts

### 7.1 Verified Facts (Confirmed from Code and Files)
- The Flask app is structured to run both locally and on Railway with eventlet monkey-patching and MongoDB Atlas integration.
- Model weights `yolo11n.pt` (5.6 MB), `FastSAM-s.pt` (23.8 MB), `yolov8n.pt` (6.5 MB), and `yolov8s-world.pt` (27.1 MB) exist physically in `Integrated_App/models/`.
- The recognition endpoint `/api/detect` supports both custom YOLO landmarks and zero-shot fallback to Gemini Vision API, with automated coordinate resolution.
- The artifact segmentation pipeline (`artifact_segmentation_pipeline.py`) successfully extracts multi-item transparent PNG crops and bounding boxes for jewelry displays (`/api/artifacts/segment`).
- An orientation-stabilized camera overlay (`ARSession` in `index.html`) is already implemented using `DeviceOrientationEvent` and `DeviceMotionEvent`, with an orientation HUD and motion indicators.
- Geohash encoding/decoding and Haversine distance calculations are fully implemented in pure Python with no external C-extension dependencies.

### 7.2 Uncertainties and Areas Requiring Physical Device Verification
- **iOS Safari Motion Permissions:** `DeviceOrientationEvent.requestPermission` requires a secure HTTPS origin and explicit user gesture; testing on a real iPhone over local network requires an HTTPS tunnel (e.g. ngrok or mkcert).
- **Gemini Live API Key:** If `GEMINI_API_KEY` is not populated in `.env`, the system uses fallback mock descriptors.
- **Railway Memory Limits:** On free/low-tier Railway instances (512MB-1GB RAM), running FastSAM or YOLO-World concurrently can trigger OOM kills, which is why single-thread limits and model aliasing were introduced.

---

## 8. Step-by-Step Instructions for Running and Testing

### 8.1 Prerequisites
- Python 3.10 - 3.13 (Python 3.13 tested in `__pycache__`).
- Git, pip, and a webcam (or smartphone browser on local network).

### 8.2 Installation and Startup
1. Open a terminal in the project directory:
   ```cmd
   cd D:\Gradautaion_Project\Integrated_App
   ```
2. Activate your virtual environment (if any) or install dependencies:
   ```cmd
   pip install -r requirements.txt
   ```
3. Set your environment variables in `.env` or `atlas-credentials.env`:
   ```env
   MONGODB_URI=your_mongodb_atlas_connection_string
   GEMINI_API_KEY=your_gemini_api_key
   ```
4. Run the application:
   ```cmd
   python app.py
   ```
   Or run the batch script:
   ```cmd
   run_app.bat
   ```
5. Access the application in your browser at:
   ```text
   http://localhost:5000
   ```
   *(For mobile AR testing with camera and gyro, access via local IP over HTTPS or use an ngrok tunnel: `ngrok http 5000`).*

### 8.3 Testing Landmark Detection and AR
1. **Landmark Detection:** On the main page, upload a picture of the Pyramids, Sphinx, or Tutankhamun Mask. Verify that the bounding box, visual instance contour glow, matched site information, and community posts appear.
2. **AR Overlay:** Click the **"Enter AR Mode"** button. Point the camera around to see the orientation-stabilized badge adjust to device tilt and yaw.
3. **Museum Artifact Mode:** Click the top navigation tab **"Museum Artifacts and Jewelry"**. Upload `test_museum_jewelry.jpg` (or click "Load Showcase Sample"). Verify that FastSAM segments each individual necklace/pendant, produces transparent crops, and renders separate cards for each item.
4. **GPS Geofencing:** Click **"Egyptian Museum"** in the GPS Simulator panel to observe real-time proximity alerts and filter community posts by location.
