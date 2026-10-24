// Each model belongs to one catalog identity. There is no generic shape fallback.
export const normalizeIdentity = value => String(value || '').trim().toLowerCase().replace(/[ _]+/g, '-');

export function resolveAsset(catalog, identity, mode, objectTrackers = new Map()) {
    if (!['image', 'object'].includes(mode)) throw new Error('Choose a photo target or a real artifact.');
    const records = catalog?.artifacts;
    if (!Array.isArray(records)) throw new Error('Invalid artifact model catalog.');
    const id = identity?.objectId;
    const name = normalizeIdentity(identity?.className || identity?.name);
    const matches = records.filter(record => id
        ? record.objectId === id
        : [record.className, ...(record.aliases || [])].some(alias => normalizeIdentity(alias) === name));
    if (matches.length !== 1) throw new Error('No unique 3D model mapping exists for this artifact.');
    const asset = matches[0];
    if (!asset.modelUrl || !/\.(glb|gltf)(?:\?.*)?$/i.test(asset.modelUrl)) {
        throw new Error(`A matching GLB or glTF asset is needed for ${asset.label}.`);
    }
    const tracking = asset.tracking?.[mode];
    if (mode === 'image' && (!tracking?.targetUrl || !Number.isInteger(tracking.targetIndex) || tracking.targetIndex < 0)) {
        throw new Error('This artifact needs a compiled image reference for photo tracking.');
    }
    if (mode === 'object' && (!tracking?.referenceUrl || !objectTrackers.has(tracking.adapter))) {
        throw new Error('Real-artifact tracking needs a scan/reference and a compatible object-pose tracker.');
    }
    const transform = tracking?.modelTransform;
    for (const field of ['position', 'rotation', 'scale']) {
        if (!Array.isArray(transform?.[field]) || transform[field].length !== 3 || !transform[field].every(Number.isFinite)) {
            throw new Error('The model needs a calibrated position, rotation and scale for this target.');
        }
    }
    if (transform.scale.some(value => value <= 0)) throw new Error('Model scale must be positive.');
    return { ...asset, mode, target: tracking };
}
