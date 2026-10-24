/* Lazy entry point: recognition supplies identity; a tracker supplies the pose. */
window.AR3DEngine = (() => {
    let current = null;
    let generation = 0;
    let pending = Promise.resolve();
    const objectTrackers = new Map();
    const moduleUrl = new URL('./ar_tracked_session.mjs', document.currentScript.src).href;
    const loadModule = () => import(moduleUrl);

    async function prepare(identity, mode) {
        const { resolveAsset } = await loadModule();
        const response = await fetch('/static/ar/artifacts.json', { cache: 'no-store' });
        if (!response.ok) throw new Error('The artifact model catalog could not be loaded.');
        return resolveAsset(await response.json(), identity, mode, objectTrackers);
    }

    async function mount(asset, options = {}) {
        const ticket = ++generation;
        const previous = current;
        current = null;
        pending = pending.catch(() => {}).then(async () => {
            if (previous) await previous.stop();
            if (ticket !== generation) return;
            const { TrackedSession } = await loadModule();
            if (ticket !== generation) return;
            const session = new TrackedSession(asset, { ...options, objectTrackers });
            current = session;
            try {
                await session.start();
                if (ticket !== generation) await session.stop();
            } catch (error) {
                await session.stop();
                if (current === session) current = null;
                throw error;
            }
        });
        return pending;
    }

    async function unmount() {
        ++generation;
        const session = current;
        current = null;
        if (session) await session.stop();
        await pending.catch(() => {});
    }

    function registerObjectTracker(name, factory) {
        if (!name || typeof factory !== 'function') throw new Error('Invalid object tracker adapter.');
        objectTrackers.set(name, factory);
    }

    return { prepare, mount, unmount, registerObjectTracker };
})();
