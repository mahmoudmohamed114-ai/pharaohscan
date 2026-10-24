# Tracked artifact models

Status: model-loading/interaction infrastructure and a MindAR image adapter are implemented. **No authentic model assets, image targets, or real-object tracking adapter are supplied. Real-artifact AR is not operational yet.** The application reports missing configuration instead of substituting a procedural shape or a gyro-anchored model.

## Asset mapping

`artifacts.json` maps one heritage object ID to its own GLB/glTF. Unknown IDs/classes never fall back to a generic artifact. Keep Khafre and Great Pyramid as separate entries/models. Source real, appropriately licensed models/scans and keep provenance alongside them. Museum `Item_01` and category `Pendant` do not identify a catalog object.

For each completed entry, configure an actual model URL and one or both tracking modes. These are **configuration examples**, not files included in the project:

```json
{
  "objectId": "O002",
  "className": "Mask-of-Tutankhamun",
  "aliases": ["Mask of Tutankhamun"],
  "label": "Mask of Tutankhamun",
  "modelUrl": "/static/models/tutankhamun_mask.glb",
  "tracking": {
    "image": {
      "targetUrl": "/static/ar/targets/tutankhamun.mind",
      "targetIndex": 0,
      "modelTransform": {"position": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1]}
    },
    "object": {
      "adapter": "your-device-specific-tracker",
      "referenceUrl": "/static/ar/references/tutankhamun-reference",
      "modelTransform": {"position": [0,0,0], "rotation": [0,0,0], "scale": [1,1,1]}
    }
  }
}
```

The example transforms are identity transforms, **not calibrated values for a mask**. Rotation is XYZ Euler radians. Image tracking units are relative to reference-image width; object tracking uses the adapter's calibrated world units (recommended metres). Determine model origin, orientation, and scale from the exact reference and asset. No automatic fit-to-bounding-box or automatic normalization occurs because it would destroy physical scale.

## Photos on a screen or board

Select “Photo on screen / board.” Compile the exact textured image using the [MindAR compiler](https://hiukim.github.io/mind-ar-js-doc/tools/compile), retain that reference image, and set targetIndex to its index in the compiled `.mind` file. Do not compile a photograph of a 3D object and claim it tracks that physical object's pose from arbitrary viewpoints.

The integration pins MindAR 1.2.5 and Three.js 0.151.3 via an import map; both loader and tracker share one Three module. Dependencies load from CDN on demand; no Python packages were added. Import maps, WebGL, HTTPS, network access, and camera permission are required. Test on the actual browsers. The tracker owns the camera/projection/anchor; content hides on target loss. Drag rotates an interaction child, never the tracked anchor; reset restores that child. Tap raycasts the visible model and opens the existing information drawer. There is no unsolicited auto-rotation.

## Real physical artifacts — required next integration

The owner chose real-artifact mode as the first target. It is the default and does not fall back to image mode. Select a device-compatible **object-pose tracking** system using the exact artifact's scan/model reference. Native ARKit reference-object detection and other model-based trackers require their own references/device capabilities; native APIs cannot simply be called from this Flask browser app. A GLB describes render geometry, not a trained tracking reference.

Before selecting a tracker, obtain the actual phone/OS/browser, the artifact's exact model/scan and physical dimensions, tracking reference requirements, deployment/licensing constraints, and desired occlusion behavior. Reflective museum glass/gold and uniform surfaces require physical validation. No object tracker is installed by this change.

An external tracker can integrate by registering:

```js
AR3DEngine.registerObjectTracker('your-device-specific-tracker', async options => {
    // options: THREE, container, objectId, referenceUrl, signal, onPose
    // Return renderer, scene, camera, anchor, async start(), async stop(), dispose().
    // This skeleton deliberately does not fabricate a pose or a camera source.
});
```

Contract:

- The adapter owns camera startup/permission and calibrated projection/view updates. Its `scene`, `camera`, `anchor` and renderer must use the supplied THREE instance. Include the anchor in the scene. `start` must reject promptly on failure and respect AbortSignal, including camera acquisition that resolves after cancellation. `stop` releases all media/sensor/network/worker resources; dispose removes its DOM/listeners. Renderer ownership/disposal is shared: engine stops its render loop and disposes it after adapter shutdown.
- Continuously call `onPose({objectId, tracked:true, matrix:[16 finite numbers]})`. Matrix is **column-major affine object-to-world** in the SAME reference frame as the adapter's camera. It must represent measured target pose, not a detector box/GPS/gyro approximation. Set camera projection and view pose coherently before the sample.
- On loss call `onPose({objectId,tracked:false})`. Engine rejects mismatched IDs/invalid matrices and hides object content when object poses stop arriving for 500ms. Tune this only using measured device performance.
- User inspection rotates the content's child group, not the measured anchor, camera, or base model calibration. No depth occlusion is implemented; add a depth/occlusion provider separately if needed.

## Checks and pending validation

Run `node --test tests/ar_tracking.test.mjs` from Integrated_App (Node 18+). It covers strict identity/model matching, no image fallback in object mode, configuration gating, and pose loss/invalidity. These tests do not prove actual pose estimation or WebGL/camera rendering.

Once genuine assets and the adapter are available: use a physical phone over HTTPS; test translations, rotations, distance/scale, target loss/reacquisition, overlapping artifacts, tapping empty space versus mesh, drag versus tap, reset, denial/retry, exit during initialization, page hide, repeat scans and restart. Validate model/target alignment with measured dimensions and known viewpoints. Confirm recognition/posts remain intact. Test photo mode separately on the exact displayed reference. Until those tests pass, do not describe this as completed real-object AR.

Recognition internals and model weights are preserved. The landmark result UI no longer displays annotated detection boxes. The museum segmentation tab remains an existing diagnostic/extraction workflow; its generic instance categories cannot select accurate catalog models without a separate identity mapping.

References: [MindAR](https://hiukim.github.io/mind-ar-js-doc/), [Three.js GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html), [Apple reference-object documentation](https://developer.apple.com/documentation/ARKit/scanning-and-detecting-3d-objects).
