import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveAsset } from '../static/js/ar_asset_registry.mjs';
import { acceptObjectPose, TrackedSession } from '../static/js/ar_tracked_session.mjs';
import { readFile } from 'node:fs/promises';

const transform = { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
const record = {
    objectId: 'O002', className: 'Mask-of-Tutankhamun', aliases: ['Mask of Tutankhamun'],
    label: 'Tutankhamun mask', modelUrl: '/static/models/mask.glb',
    tracking: {
        image: { targetUrl: '/static/ar/mask.mind', targetIndex: 0, modelTransform: transform },
        object: { adapter: 'test-pose', referenceUrl: '/static/ar/mask.ref', modelTransform: transform }
    }
};
const catalog = { artifacts: [record] };
const identity = { objectId: 'O002', name: 'Mask of Tutankhamun' };

test('identity resolves an exact model and preserves target-specific calibration', () => {
    const asset = resolveAsset(catalog, identity, 'image');
    assert.equal(asset.modelUrl, record.modelUrl);
    assert.equal(asset.target.targetIndex, 0);
    assert.deepEqual(asset.target.modelTransform, transform);
    assert.equal(resolveAsset(catalog, { name: 'mask of tutankhamun' }, 'image').objectId, 'O002');
});

test('an unknown identity, ambiguous mapping, or conflicting authoritative ID cannot select a substitute', () => {
    for (const other of [{ name: 'Unknown artifact' }, { name: 'mask' }, { objectId: 'O999', name: identity.name }]) {
        assert.throws(() => resolveAsset(catalog, other, 'image'), /unique/);
    }
    assert.throws(() => resolveAsset({ artifacts: [record, record] }, identity, 'image'), /unique/);
});

test('real physical mode never silently falls back to image tracking', () => {
    assert.throws(() => resolveAsset(catalog, identity, 'object'), /object-pose tracker/);
    const adapters = new Map([['test-pose', () => {}]]);
    assert.equal(resolveAsset(catalog, identity, 'object', adapters).mode, 'object');
    const missingReference = structuredClone(catalog);
    missingReference.artifacts[0].tracking.object.referenceUrl = null;
    assert.throws(() => resolveAsset(missingReference, identity, 'object', adapters), /scan\/reference/);
});

test('missing assets and invalid calibration are reported before camera acquisition', async () => {
    const actual = JSON.parse(await readFile(new URL('../static/ar/artifacts.json', import.meta.url)));
    assert.throws(() => resolveAsset(actual, identity, 'object'), /GLB or glTF/);
    const badScale = structuredClone(catalog);
    badScale.artifacts[0].tracking.image.modelTransform.scale[0] = 0;
    assert.throws(() => resolveAsset(badScale, identity, 'image'), /positive/);
    const badRotation = structuredClone(catalog);
    badRotation.artifacts[0].tracking.image.modelTransform.rotation[0] = NaN;
    assert.throws(() => resolveAsset(badRotation, identity, 'image'), /calibrated/);
});

const matrix = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0.2, 0.4, -1, 1];
function anchor() {
    return { visible: false, matrix: { fromArray(value) { this.elements = [...value]; } } };
}

test('pose updates translate the anchor and hide it on loss or wrong identity', () => {
    const target = anchor();
    assert.equal(acceptObjectPose(target, { tracked: true, objectId: 'O002', matrix }, 'O002'), true);
    assert.deepEqual(target.matrix.elements.slice(12, 15), [0.2, 0.4, -1]);
    assert.equal(target.matrixAutoUpdate, false);
    assert.equal(target.matrixWorldNeedsUpdate, true);
    assert.equal(acceptObjectPose(target, { tracked: false }, 'O002'), false);
    assert.equal(target.visible, false);
    assert.equal(acceptObjectPose(target, { tracked: true, objectId: 'O003', matrix }, 'O002'), false);
    assert.equal(target.visible, false);
});

test('invalid, singular, nonfinite and projection matrices cannot become object poses', () => {
    const cases = [[], Array(16).fill(0), matrix.map((v, i) => i === 12 ? NaN : v), matrix.map((v, i) => i === 15 ? 0 : v)];
    for (const value of cases) {
        assert.equal(acceptObjectPose(anchor(), { tracked: true, objectId: 'O002', matrix: value }, 'O002'), false);
    }
});

// No WebGL, physical camera, neural model or service is started by these lifecycle checks.
class TestSession extends TrackedSession {
    constructor(loadModel) {
        const options = { container: {}, objectTrackers: new Map() };
        super({ ...record, mode: 'object', target: record.tracking.object }, options);
        this.loadModel = loadModel;
        this.calls = { rendererDisposed: 0, trackerStopped: 0, modelDisposed: 0 };
    }
    loadRenderingModules() {
        const session = this;
        class Group {
            rotation = { set() {} };
            add() {}
        }
        return [{ Group, Clock: class { getDelta() { return 0.016; } } }, {
            GLTFLoader: class { loadAsync() { return session.loadModel(); } }
        }];
    }
    async startObjectTracker() {
        this.anchor = anchor();
        this.renderer = {
            setAnimationLoop: fn => { this.frame = fn; },
            render() {}, dispose: () => this.calls.rendererDisposed++, domElement: { remove() {} }
        };
        this.scene = {}; this.camera = {};
        this.tracker = { stop: async () => { this.calls.trackerStopped++; } };
    }
    bindInteraction() {}
    modelFixture() {
        return { scene: {
            position: { fromArray() {} }, rotation: { fromArray() {} }, scale: { fromArray() {} },
            traverse: callback => callback({ geometry: { dispose: () => this.calls.modelDisposed++ } }),
            removeFromParent() {}
        }, animations: [] };
    }
}

test('a stale real-object pose is hidden, and stop is idempotent', async () => {
    globalThis.window = { isSecureContext: true };
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: { mediaDevices: { getUserMedia() {} } } });
    const session = new TestSession(() => Promise.resolve(session.modelFixture()));
    await session.start();
    session.anchor.visible = true;
    session.lastPoseTime = performance.now() - 600;
    session.frame();
    assert.equal(session.anchor.visible, false);
    await session.stop();
    await session.stop();
    assert.deepEqual(session.calls, { rendererDisposed: 1, trackerStopped: 1, modelDisposed: 1 });
});

test('exit during model loading disposes the late model without starting a camera tracker', async () => {
    let resolve;
    const session = new TestSession(() => new Promise(done => { resolve = done; }));
    const started = session.start();
    await Promise.resolve();
    await session.stop();
    resolve(session.modelFixture());
    await started;
    assert.deepEqual(session.calls, { rendererDisposed: 0, trackerStopped: 0, modelDisposed: 1 });
});

test('camera/tracker startup cancellation does not wait forever for readiness', async () => {
    const session = new TestSession(() => {});
    const starting = session.waitForStart(new Promise(() => {}));
    const assertion = assert.rejects(starting, /cancelled/);
    await session.stop();
    await assertion;
});
