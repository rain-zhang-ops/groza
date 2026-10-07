// Groza: 为自研请求注入当前集合（X-Tenant），实现多集合隔离。
export default defineNuxtPlugin(() => {
  const prefs = useViewPreferences();
  const gxFetch = $fetch.create({
    onRequest({ options }) {
      const id = prefs?.value?.collectionId;
      if (id) {
        const h = new Headers((options.headers as HeadersInit) || undefined);
        if (!h.has("X-Tenant")) h.set("X-Tenant", id);
        options.headers = h;
      }
    },
  });
  return { provide: { gxFetch } };
});
