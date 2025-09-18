import axios from 'axios';
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';
export const api = axios.create({
    baseURL: API_BASE,
});
// Config
export async function loadConfig() {
    const { data } = await api.get('/api/config');
    return data;
}
export async function saveConfig(config) {
    await api.post('/api/config', { config });
}
// Telegram auth
export async function tgLoginStart(payload) {
    const { data } = await api.post('/api/telegram/login/start', payload);
    return data;
}
export async function tgLoginComplete(payload) {
    const { data } = await api.post('/api/telegram/login/complete', payload);
    return data;
}
// Exports
export async function startTelegramExport(payload) {
    const { data } = await api.post('/api/telegram/extract', payload);
    return data;
}
export async function startSlackExport(payload) {
    const { data } = await api.post('/api/slack/extract', payload);
    return data;
}
export async function getTask(taskId) {
    const { data } = await api.get(`/api/tasks/${taskId}`);
    return data;
}
export async function testSlack(token) {
    const { data } = await api.post('/api/slack/test', { token });
    return data;
}
export async function testNotion(api_key, dest_type, parent_id) {
    const { data } = await api.post('/api/notion/test', { api_key, dest_type, parent_id });
    return data;
}
export async function searchNotion(api_key, query, type) {
    const { data } = await api.post('/api/notion/search', { api_key, query, type: type === 'all' ? undefined : type });
    return data;
}
export async function listSlackChannels(token, query, limit = 500) {
    const { data } = await api.post('/api/slack/channels', { token, query, limit });
    return data;
}
// Discord
export async function testDiscord(token) {
    const { data } = await api.post('/api/discord/test', { token });
    return data;
}
export async function listDiscordChannels(token, guild_id, query) {
    const { data } = await api.post('/api/discord/channels', { token, guild_id, query });
    return data;
}
export async function startDiscordExport(payload) {
    const { data } = await api.post('/api/discord/extract', payload);
    return data;
}
