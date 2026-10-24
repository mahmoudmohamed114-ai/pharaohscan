import { resolveAsset } from './ar_asset_registry.mjs';
export { resolveAsset };

// Only a tracker may write the anchor transform. User interaction rotates its child.
export function acceptObjectPose(anchor, sample, objectId) {
    const matrix = sample?.matrix;
    const determinant = Array.isArray(matrix) && matrix.length === 16
        ? matrix[0] * (matrix[5] * matrix[10] - matrix[6] * matrix[9]) -
          matrix[4] * (matrix[1] * matrix[10] - matrix[2] * matrix[9]) +
          matrix[8] * (matrix[1] * matrix[6] - matrix[2] * matrix[5]) : 0;
    const valid = sample?.tracked === true && sample.objectId === objectId &&
        Array.isArray(matrix) && matrix.length === 16 && matrix.every(Number.isFinite) &&
        Math.abs(determinant) > 1e-8 && matrix[15] === 1 &&
        [matrix[3], matrix[7], matrix[11]].every(value => Math.abs(value) < 1e-6);
    anchor.visible = valid;
    if (valid) {
        anchor.matrixAutoUpdate = false;
        anchor.matrix.fromArray(matrix);
        anchor.matrixWorldNeedsUpdate = true;
    }
    return valid;
}

function disposeModel(root) {
    const textures = new Set();
    root?.traverse(node => {
        node.geometry?.dispose();
        for (const material of [node.material].flat().filter(Boolean)) {
            for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
            material.dispose();
        }
    });
    for (const texture of textures) texture.dispose();
}

export class TrackedSession {
    constructor(asset, options) {
        this.asset = asset;
        this.options = options;
        this.cancelled = false;
        this.abort = new AbortController();
        this.mixers = [];
        this.pointers = new Map();
    }

    status(message, tracked = false) { this.options.onStatus?.(message, tracked); }

    async waitForStart(promise) {
        let timeout;
        let cancel;
        const interrupted = new Promise((_, reject) => {
            cancel = () => reject(new Error('AR startup was cancelled.'));
            this.abort.signal.addEventListener('abort', cancel, { once: true });
            if (this.abort.signal.aborted) cancel();
            timeout = setTimeout(() => reject(new Error('Tracking startup timed out. Please retry.')), 30000);
        });
        try { await Promise.race([promise, interrupted]); }
        finally {
            clearTimeout(timeout);
            this.abort.signal.removeEventListener('abort', cancel);
        }
    }

    loadRenderingModules() {
        return Promise.all([import('three'), import('three/addons/loaders/GLTFLoader.js')]);
    }

    async start() {
        if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
            throw new Error('Tracked AR needs HTTPS and camera permission on a physical device.');
        }
        this.status('Loading the matching 3D model…');
        const [THREE, loaderModule] = await this.loadRenderingModules();
        if (this.cancelled) return;
        this.THREE = THREE;
        const gltf = await new loaderModule.GLTFLoader().loadAsync(this.asset.modelUrl);
        this.model = gltf.scene;
        if (this.cancelled) { disposeModel(this.model); this.model = null; return; }
        const transform = this.asset.target.modelTransform;
        this.model.position.fromArray(transform.position);
        this.model.rotation.fromArray([...transform.rotation, 'XYZ']);
        this.model.scale.fromArray(transform.scale);
        this.interaction = new THREE.Group();
        this.interaction.add(this.model);
        this.clock = new THREE.Clock();
        if (gltf.animations?.length) {
            const mixer = new THREE.AnimationMixer(this.model);
            this.mixers.push(mixer);
            for (const clip of gltf.animations) mixer.clipAction(clip).play();
        }

        if (this.asset.mode === 'image') await this.startImageTracker();
        else await this.startObjectTracker();
        if (this.cancelled) { await this.stop(); return; }
        this.bindInteraction();
        this.renderer.setAnimationLoop(() => {
            if (this.cancelled) return;
            if (this.asset.mode === 'object' && this.anchor.visible &&
                performance.now() - this.lastPoseTime > 500) {
                this.anchor.visible = false;
                this.pointers.clear();
                this.status('Tracking paused · reacquire the artifact');
            }
            const dt = Math.min(this.clock.getDelta(), 0.1);
            for (const mixer of this.mixers) mixer.update(dt);
            this.renderer.render(this.scene, this.camera);
        });
        if (!this.anchor.visible) this.status('Point the camera at the matching reference target.');
    }

    async startImageTracker() {
        const { MindARThree } = await import('https://cdn.jsdelivr.net/npm/mind-ar@1.2.5/dist/mindar-image-three.prod.js');
        if (this.cancelled) return;
        // MindAR 1.2.5 registers a bound resize callback without a dispose API.
        // Capture that exact callback through a small subclass so stop can remove it.
        class DisposableMindAR extends MindARThree {
            get resize() {
                if (!this.savedResize) {
                    this.savedResize = (...args) => MindARThree.prototype.resize.apply(this, args);
                    this.savedResize.bind = () => this.savedResize;
                }
                return this.savedResize;
            }
        }
        this.tracker = new DisposableMindAR({
            container: this.options.container,
            imageTargetSrc: this.asset.target.targetUrl,
            maxTrack: 1, uiLoading: 'no', uiScanning: 'no', uiError: 'no'
        });
        this.renderer = this.tracker.renderer;
        this.tracker.cssRenderer.domElement.style.pointerEvents = 'none';
        this.scene = this.tracker.scene;
        this.camera = this.tracker.camera;
        const anchor = this.tracker.addAnchor(this.asset.target.targetIndex);
        this.anchor = anchor.group;
        this.anchor.add(this.interaction);
        anchor.onTargetFound = () => this.status('Photo tracked · drag the model to rotate · tap for information', true);
        anchor.onTargetLost = () => {
            this.pointers.clear();
            this.status('Target lost · point the camera back at the photo');
        };
        this.addLights();
        // Retain the startup promise so stop also releases late camera acquisition.
        this.startup = this.tracker.start();
        // The library can acquire a camera after cancellation; release that late stream too.
        this.startup.then(() => {
            if (this.cancelled) {
                this.tracker.controller?.stopProcessVideo();
                this.tracker.video?.srcObject?.getTracks().forEach(track => track.stop());
                this.tracker.video?.remove();
            }
        }, () => {});
        await this.waitForStart(this.startup);
    }

    async startObjectTracker() {
        const factory = this.options.objectTrackers.get(this.asset.target.adapter);
        if (!factory) throw new Error('No compatible real-artifact tracker is installed.');
        const tracker = await factory({
            THREE: this.THREE, container: this.options.container,
            objectId: this.asset.objectId, referenceUrl: this.asset.target.referenceUrl,
            signal: this.abort.signal,
            onPose: sample => {
                if (this.cancelled || !this.anchor) return;
                const tracked = acceptObjectPose(this.anchor, sample, this.asset.objectId);
                this.lastPoseTime = performance.now();
                if (!tracked) this.pointers.clear();
                this.status(tracked ? 'Artifact tracked · drag to rotate · tap for information' : 'Artifact lost · reacquire it', tracked);
            }
        });
        this.tracker = tracker;
        if (this.cancelled) { await tracker.stop?.(); tracker.dispose?.(); return; }
        for (const key of ['renderer', 'scene', 'camera', 'anchor']) {
            if (!tracker[key]) throw new Error(`Object tracker is missing ${key}.`);
            this[key] = tracker[key];
        }
        if (typeof tracker.start !== 'function' || typeof tracker.stop !== 'function') {
            throw new Error('Object tracker must implement start and stop.');
        }
        this.anchor.visible = false;
        this.anchor.add(this.interaction);
        this.addLights();
        this.startup = tracker.start();
        await this.waitForStart(this.startup);
    }

    addLights() {
        this.light = new this.THREE.HemisphereLight(0xffffff, 0x444444, 1.4);
        this.scene.add(this.light);
        this.keyLight = new this.THREE.DirectionalLight(0xffffff, 1.5);
        this.keyLight.position.set(1, 2, 3);
        this.scene.add(this.keyLight);
    }

    bindInteraction() {
        const canvas = this.renderer.domElement;
        canvas.style.touchAction = 'none';
        this.raycaster = new this.THREE.Raycaster();
        this.options.container.addEventListener('reset-model', () => {
            this.interaction.rotation.set(0, 0, 0);
        }, { signal: this.abort.signal });
        const hitsModel = event => {
            if (!this.anchor.visible) return false;
            const rect = canvas.getBoundingClientRect();
            this.scene.updateMatrixWorld(true);
            this.camera.updateMatrixWorld(true);
            this.raycaster.setFromCamera(new this.THREE.Vector2(
                (event.clientX - rect.left) / rect.width * 2 - 1,
                -(event.clientY - rect.top) / rect.height * 2 + 1
            ), this.camera);
            return this.raycaster.intersectObject(this.interaction, true).length > 0;
        };
        canvas.addEventListener('pointerdown', event => {
            if (!hitsModel(event) || this.pointers.size) return;
            canvas.setPointerCapture(event.pointerId);
            this.pointers.set(event.pointerId, {
                x: event.clientX, y: event.clientY,
                rx: this.interaction.rotation.x, ry: this.interaction.rotation.y, moved: false
            });
        }, { signal: this.abort.signal });
        canvas.addEventListener('pointermove', event => {
            const start = this.pointers.get(event.pointerId);
            if (!start || !this.anchor.visible) return;
            const dx = event.clientX - start.x, dy = event.clientY - start.y;
            start.moved ||= Math.hypot(dx, dy) > 8;
            if (start.moved) {
                this.interaction.rotation.y = start.ry + dx * 0.008;
                this.interaction.rotation.x = Math.max(-Math.PI / 2, Math.min(Math.PI / 2, start.rx + dy * 0.008));
            }
        }, { signal: this.abort.signal });
        canvas.addEventListener('pointerup', event => {
            const start = this.pointers.get(event.pointerId);
            this.pointers.delete(event.pointerId);
            if (start && !start.moved && hitsModel(event)) this.options.onInspect?.(this.asset);
        }, { signal: this.abort.signal });
        for (const type of ['pointercancel', 'lostpointercapture']) {
            canvas.addEventListener(type, event => this.pointers.delete(event.pointerId), { signal: this.abort.signal });
        }
    }

    async stop() {
        if (this.stopping) return this.stopping;
        this.cancelled = true;
        this.abort.abort();
        this.renderer?.setAnimationLoop(null);
        this.stopping = this.cleanup();
        return this.stopping;
    }

    async cleanup() {
        this.pointers.clear();
        const tracker = this.tracker;
        if (tracker) {
            // Stop a ready camera immediately, and also after a pending start resolves.
            try { tracker.controller?.stopProcessVideo(); } catch (_) { /* not initialized */ }
            tracker.video?.srcObject?.getTracks().forEach(track => track.stop());
            if (this.asset.mode === 'image') {
                try { tracker.controller?.stopProcessVideo(); } catch (_) { /* partial startup */ }
                tracker.video?.srcObject?.getTracks().forEach(track => track.stop());
                tracker.video?.remove();
                window.removeEventListener('resize', tracker.savedResize);
                tracker.cssRenderer?.domElement.remove();
            } else {
                await tracker.stop?.();
                tracker.dispose?.();
            }
        }
        for (const mixer of this.mixers) { mixer.stopAllAction(); mixer.uncacheRoot(this.model); }
        this.mixers = [];
        disposeModel(this.model);
        this.model?.removeFromParent();
        this.light?.removeFromParent();
        this.keyLight?.removeFromParent();
        this.renderer?.dispose();
        this.renderer?.domElement.remove();
    }
}
