// Runs every 10 minutes on Cloudflare. Publishes scheduled posts, sends waiting
// site rebuilds, and keeps the free backend and database from going to sleep.
export default {
  async scheduled(_event, env, ctx) {
    const call = (path) =>
      fetch(`${env.API_BASE_URL}${path}`, { method: 'POST', headers: { 'X-Cron-Secret': env.BLOG_CRON_SECRET } })
        .then((res) => { if (!res.ok) console.error(path, res.status) })
        .catch((err) => console.error(path, err))
    ctx.waitUntil(Promise.all([call('/api/v1/internal/blogs/publish-due'), call('/api/v1/internal/site-builds/flush')]))
  },
}
