import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useMemo, useState } from 'react';
import { api, getTask, loadConfig, saveConfig, startSlackExport, startTelegramExport, testNotion, testSlack, tgLoginComplete, tgLoginStart, searchNotion, listSlackChannels, } from './api';
function Section({ title, children }) {
    return (_jsxs("div", { style: { border: '1px solid #ddd', borderRadius: 8, padding: 12, marginBottom: 16 }, children: [_jsx("div", { style: { fontWeight: 600, marginBottom: 8 }, children: title }), children] }));
}
function Row({ children }) {
    return _jsx("div", { style: { display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }, children: children });
}
function TextInput(props) {
    return _jsx("input", { ...props, style: { ...(props.style || {}), padding: '6px 8px', width: props.style?.width || 280 } });
}
function Select(props) {
    return _jsx("select", { ...props, style: { ...(props.style || {}), padding: '6px 8px', width: props.style?.width || 280 } });
}
export default function App() {
    const [cfg, setCfg] = useState(null);
    const [tab, setTab] = useState('extract');
    const [busy, setBusy] = useState(false);
    const [task, setTask] = useState(null);
    const [taskId, setTaskId] = useState(null);
    useEffect(() => {
        loadConfig().then(setCfg);
    }, []);
    useEffect(() => {
        if (!taskId)
            return;
        setTask(null);
        const t = setInterval(async () => {
            try {
                const st = await getTask(taskId);
                setTask(st);
                if (st.status !== 'running')
                    clearInterval(t);
            }
            catch (e) {
                clearInterval(t);
            }
        }, 800);
        return () => clearInterval(t);
    }, [taskId]);
    if (!cfg)
        return _jsx("div", { style: { padding: 16 }, children: "Loading..." });
    const dfl = cfg.defaults || {};
    const [tgApiId, setTgApiId] = useState(cfg.telegram?.api_id || '');
    const [tgApiHash, setTgApiHash] = useState(cfg.telegram?.api_hash || '');
    const [tgPhone, setTgPhone] = useState(cfg.telegram?.phone || '');
    const [tgSession, setTgSession] = useState(cfg.telegram?.session || '');
    const [slackToken, setSlackToken] = useState(cfg.slack?.token || '');
    const [dest, setDest] = useState(dfl.destination || 'Folder (local)');
    const [format, setFormat] = useState(dfl.format || 'jsonl');
    const [reverse, setReverse] = useState(!!dfl.reverse);
    const [resume, setResume] = useState(!!dfl.resume);
    const [only, setOnly] = useState(dfl.only || 'all');
    const [limit, setLimit] = useState('');
    const [minDate, setMinDate] = useState('');
    const [maxDate, setMaxDate] = useState('');
    const [users, setUsers] = useState('');
    const [keywords, setKeywords] = useState('');
    const [chat, setChat] = useState('');
    const [media, setMedia] = useState(false);
    const [outFolder, setOutFolder] = useState(dfl.last_output_folder || '');
    const [filename, setFilename] = useState(dfl.filename || 'messages.jsonl');
    const notionDests = cfg.notion?.destinations || [];
    const notionNames = notionDests.map((d) => d.name);
    const [notionSel, setNotionSel] = useState(notionNames[0] || '');
    const selectedNotion = useMemo(() => notionDests.find((d) => d.name === notionSel), [notionSel, notionDests]);
    const [notionMode, setNotionMode] = useState(dfl.notion_mode || 'per_message');
    const fsOutPath = `${outFolder.replace(/\\+$/, '')}/${filename}`;
    async function handleSaveSettings() {
        const next = {
            ...cfg,
            telegram: { api_id: tgApiId, api_hash: tgApiHash, phone: tgPhone, session: tgSession || undefined },
            slack: { token: slackToken },
            defaults: { ...cfg.defaults, format, reverse, resume, destination: dest, only, last_output_folder: outFolder, filename, notion_mode: notionMode },
        };
        await saveConfig(next);
        setCfg(next);
        alert('Settings saved');
    }
    async function doTgTestLogin() {
        setBusy(true);
        try {
            await tgLoginStart({ api_id: Number(tgApiId), api_hash: tgApiHash, phone: tgPhone, session: tgSession || undefined });
            const code = window.prompt('Enter Telegram login code:') || '';
            if (!code)
                return;
            const password = window.prompt('If you have 2FA password, enter it (or leave blank):') || undefined;
            await tgLoginComplete({ api_id: Number(tgApiId), api_hash: tgApiHash, phone: tgPhone, code, password, session: tgSession || undefined });
            alert('Telegram login OK. Session saved.');
        }
        catch (e) {
            alert('Login failed: ' + (e?.response?.data?.detail || e.message || e));
        }
        finally {
            setBusy(false);
        }
    }
    async function doTestSlack() {
        setBusy(true);
        try {
            const res = await testSlack(slackToken);
            alert(res.message);
        }
        catch (e) {
            alert('Slack error: ' + (e?.response?.data?.detail || e.message || e));
        }
        finally {
            setBusy(false);
        }
    }
    async function doTestNotion() {
        const nd = selectedNotion;
        if (!nd)
            return alert('Pick a Notion destination in Settings');
        setBusy(true);
        try {
            const res = await testNotion(nd.api_key, nd.type, nd.parent_id);
            alert(res.message);
        }
        catch (e) {
            alert('Notion error: ' + (e?.response?.data?.detail || e.message || e));
        }
        finally {
            setBusy(false);
        }
    }
    async function doExtract() {
        setBusy(true);
        setTaskId(null);
        setTask(null);
        try {
            const common = {
                reverse,
                resume,
                limit: limit ? Number(limit) : undefined,
                min_date: minDate || undefined,
                max_date: maxDate || undefined,
                only_media: only === 'media',
                only_text: only === 'text',
                users: users ? users.split(',').map((s) => s.trim()).filter(Boolean) : undefined,
                keywords: keywords ? keywords.split(',').map((s) => s.trim()).filter(Boolean) : undefined,
            };
            let start;
            if ((cfg.app || 'Telegram').startsWith('Telegram')) {
                const payload = {
                    api_id: Number(tgApiId),
                    api_hash: tgApiHash,
                    session: tgSession || undefined,
                    chat,
                    media_dir: media ? (outFolder + '/media') : undefined,
                    ...common,
                };
                if (dest.startsWith('Notion') && selectedNotion) {
                    payload.notion_api_key = selectedNotion.api_key;
                    payload.notion_dest_type = selectedNotion.type;
                    payload.notion_parent_id = selectedNotion.parent_id;
                    payload.notion_mode = notionMode;
                }
                else {
                    payload.out = fsOutPath;
                    payload.format = format;
                }
                start = startTelegramExport(payload);
            }
            else {
                const payload = {
                    token: slackToken,
                    channel: chat,
                    media_dir: media ? (outFolder + '/media') : undefined,
                    ...common,
                };
                if (dest.startsWith('Notion') && selectedNotion) {
                    payload.notion_api_key = selectedNotion.api_key;
                    payload.notion_dest_type = selectedNotion.type;
                    payload.notion_parent_id = selectedNotion.parent_id;
                    payload.notion_mode = notionMode;
                }
                else {
                    payload.out = fsOutPath;
                    payload.format = format;
                }
                start = startSlackExport(payload);
            }
            const { task_id } = await start;
            setTaskId(task_id);
        }
        catch (e) {
            alert('Start error: ' + (e?.response?.data?.detail || e.message || e));
        }
        finally {
            setBusy(false);
        }
    }
    function ExtractTab() {
        const appOptions = ['Telegram', 'Slack (coming soon)', 'Teams (coming soon)'];
        return (_jsxs("div", { children: [_jsxs(Section, { title: "Extract", children: [_jsxs(Row, { children: [_jsx("label", { children: "Chat Application:" }), _jsx(Select, { value: cfg.app || 'Telegram', onChange: (e) => setCfg({ ...cfg, app: e.currentTarget.value }), children: appOptions.map((o) => (_jsx("option", { value: o, children: o }, o))) })] }), _jsxs(Row, { children: [_jsx("label", { children: "Chat / Channel:" }), _jsx(TextInput, { value: chat, onChange: (e) => setChat(e.target.value), placeholder: "@username / link / id or #name" }), (cfg.app || 'Telegram').startsWith('Slack') && (_jsx("button", { onClick: () => setShowSlackPicker(true), children: "Pick Channel\u2026" }))] }), _jsxs(Row, { children: [_jsx("label", { children: "Min Date (YYYY-MM-DD):" }), _jsx(TextInput, { value: minDate, onChange: (e) => setMinDate(e.target.value), style: { width: 150 } }), _jsx("label", { children: "Max Date (YYYY-MM-DD):" }), _jsx(TextInput, { value: maxDate, onChange: (e) => setMaxDate(e.target.value), style: { width: 150 } })] }), _jsxs(Row, { children: [_jsx("label", { children: "Content:" }), _jsxs(Select, { value: only, onChange: (e) => setOnly(e.currentTarget.value), style: { width: 160 }, children: [_jsx("option", { value: "all", children: "All" }), _jsx("option", { value: "media", children: "Only media" }), _jsx("option", { value: "text", children: "Only text" })] }), _jsx("label", { children: "Format:" }), _jsxs(Select, { value: format, onChange: (e) => setFormat(e.currentTarget.value), style: { width: 120 }, children: [_jsx("option", { value: "jsonl", children: "jsonl" }), _jsx("option", { value: "csv", children: "csv" })] }), _jsx("label", { children: "Limit:" }), _jsx(TextInput, { value: limit, onChange: (e) => setLimit(e.target.value), style: { width: 100 } })] }), _jsxs(Row, { children: [_jsx("label", { children: "Users (comma ids/usernames):" }), _jsx(TextInput, { value: users, onChange: (e) => setUsers(e.target.value), style: { width: 420 } })] }), _jsxs(Row, { children: [_jsx("label", { children: "Keywords (comma):" }), _jsx(TextInput, { value: keywords, onChange: (e) => setKeywords(e.target.value), style: { width: 420 } })] }), _jsxs(Row, { children: [_jsxs("label", { children: [_jsx("input", { type: "checkbox", checked: reverse, onChange: (e) => setReverse(e.target.checked) }), " Oldest \u2192 newest"] }), _jsxs("label", { children: [_jsx("input", { type: "checkbox", checked: resume, onChange: (e) => setResume(e.target.checked) }), " Resume (JSONL)"] }), _jsxs("label", { children: [_jsx("input", { type: "checkbox", checked: media, onChange: (e) => setMedia(e.target.checked) }), " Download media"] })] }), _jsxs(Row, { children: [_jsx("label", { children: "Destination:" }), _jsxs(Select, { value: dest, onChange: (e) => setDest(e.currentTarget.value), style: { width: 220 }, children: [_jsx("option", { children: "Folder (local)" }), _jsx("option", { children: "Notion (saved destination)" })] })] }), dest.startsWith('Folder') ? (_jsxs(_Fragment, { children: [_jsxs(Row, { children: [_jsx("label", { children: "Output folder:" }), _jsx(TextInput, { value: outFolder, onChange: (e) => setOutFolder(e.target.value), style: { width: 420 } })] }), _jsxs(Row, { children: [_jsx("label", { children: "Filename:" }), _jsx(TextInput, { value: filename, onChange: (e) => setFilename(e.target.value), style: { width: 260 } })] })] })) : (_jsx(_Fragment, { children: _jsxs(Row, { children: [_jsx("label", { children: "Notion destination:" }), _jsxs(Select, { value: notionSel, onChange: (e) => setNotionSel(e.currentTarget.value), style: { width: 320 }, children: [notionNames.length === 0 && _jsx("option", { children: "(none saved)" }), notionNames.map((n) => (_jsx("option", { value: n, children: n }, n)))] }), _jsx("label", { children: "Mode:" }), _jsxs(Select, { value: notionMode, onChange: (e) => setNotionMode(e.currentTarget.value), style: { width: 160 }, children: [_jsx("option", { value: "per_message", children: "per_message" }), _jsx("option", { value: "group_by_day", children: "group_by_day" })] }), _jsx("button", { onClick: doTestNotion, children: "Test Notion" })] }) })), _jsx(Row, { children: _jsx("button", { disabled: busy, onClick: doExtract, children: busy ? 'Starting…' : 'Extract' }) })] }), taskId && (_jsxs(Section, { title: `Task ${taskId}`, children: [_jsxs(Row, { children: [_jsxs("div", { children: ["Status: ", task?.status || 'running'] }), task?.result && _jsxs("div", { children: ["Result: ", JSON.stringify(task.result)] }), task?.error && _jsxs("div", { style: { color: 'red' }, children: ["Error: ", task.error] })] }), _jsx("div", { style: { maxHeight: 300, overflow: 'auto', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12, background: '#fafafa', padding: 8, border: '1px solid #eee' }, children: (task?.logs || []).map((l, i) => (_jsx("div", { children: l }, i))) })] }))] }));
    }
    function SettingsTab() {
        const [showNotionPicker, setShowNotionPicker] = useState(false);
        const [searchQ, setSearchQ] = useState('');
        const [searchResults, setSearchResults] = useState([]);
        const [nName, setNName] = useState('');
        const [nKey, setNKey] = useState('');
        const [nType, setNType] = useState('Database');
        const [nParent, setNParent] = useState('');
        function addOrUpdateNotion() {
            const dests = [...(cfg.notion?.destinations || [])];
            const idx = dests.findIndex((d) => d.name === nName);
            const rec = { name: nName, api_key: nKey, type: nType, parent_id: nParent };
            if (idx >= 0)
                dests[idx] = rec;
            else
                dests.push(rec);
            const next = { ...cfg, notion: { destinations: dests } };
            setCfg(next);
        }
        async function openNotionPicker() {
            if (!nKey)
                return alert('Enter Notion API Key first');
            setSearchQ('');
            setSearchResults([]);
            setShowNotionPicker(true);
        }
        async function runNotionSearch() {
            if (!nKey)
                return alert('Enter Notion API Key first');
            const res = await searchNotion(nKey, searchQ || '');
            setSearchResults(res.results);
        }
        return (_jsxs("div", { children: [_jsxs(Section, { title: "Telegram", children: [_jsxs(Row, { children: [_jsx("label", { children: "API ID:" }), _jsx(TextInput, { value: tgApiId, onChange: (e) => setTgApiId(e.target.value) }), _jsx("label", { children: "API Hash:" }), _jsx(TextInput, { value: tgApiHash, onChange: (e) => setTgApiHash(e.target.value) })] }), _jsxs(Row, { children: [_jsx("label", { children: "Phone:" }), _jsx(TextInput, { value: tgPhone, onChange: (e) => setTgPhone(e.target.value) }), _jsx("label", { children: "Session (optional):" }), _jsx(TextInput, { value: tgSession, onChange: (e) => setTgSession(e.target.value) })] }), _jsx(Row, { children: _jsx("button", { disabled: busy, onClick: doTgTestLogin, children: "Test Login" }) })] }), _jsx(Section, { title: "Slack", children: _jsxs(Row, { children: [_jsx("label", { children: "Token:" }), _jsx(TextInput, { value: slackToken, onChange: (e) => setSlackToken(e.target.value), style: { width: 420 } }), _jsx("button", { disabled: busy, onClick: doTestSlack, children: "Test Slack" })] }) }), _jsxs(Section, { title: "Notion Destinations", children: [_jsxs(Row, { children: [_jsx("label", { children: "Name:" }), _jsx(TextInput, { value: nName, onChange: (e) => setNName(e.target.value) }), _jsx("label", { children: "API Key:" }), _jsx(TextInput, { value: nKey, onChange: (e) => setNKey(e.target.value), style: { width: 340 } })] }), _jsxs(Row, { children: [_jsx("label", { children: "Type:" }), _jsxs(Select, { value: nType, onChange: (e) => setNType(e.currentTarget.value), style: { width: 160 }, children: [_jsx("option", { children: "Database" }), _jsx("option", { children: "Page" })] }), _jsx("label", { children: "Parent ID:" }), _jsx(TextInput, { value: nParent, onChange: (e) => setNParent(e.target.value), style: { width: 360 } }), _jsx("button", { onClick: openNotionPicker, children: "Pick Parent\u2026" }), _jsx("button", { onClick: addOrUpdateNotion, children: "Save Destination" })] }), _jsxs("div", { children: ["Saved: ", notionDests.length ? notionDests.map((d) => d.name).join(', ') : '(none)'] })] }), _jsx(Row, { children: _jsx("button", { onClick: handleSaveSettings, children: "Save Settings" }) }), showNotionPicker && (_jsx("div", { style: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }, children: _jsxs("div", { style: { background: 'white', padding: 16, borderRadius: 8, width: 720, maxHeight: 560, display: 'flex', flexDirection: 'column', gap: 8 }, children: [_jsx("div", { style: { fontWeight: 600 }, children: "Pick Notion Parent" }), _jsxs("div", { style: { display: 'flex', gap: 8 }, children: [_jsx(TextInput, { value: searchQ, onChange: (e) => setSearchQ(e.target.value), placeholder: "Search pages/databases by title", style: { width: 480 } }), _jsx("button", { onClick: runNotionSearch, children: "Search" })] }), _jsx("div", { style: { overflow: 'auto', border: '1px solid #eee', flex: 1 }, children: searchResults.map((r) => (_jsxs("div", { style: { padding: 6, borderBottom: '1px solid #f0f0f0', display: 'flex', gap: 8, alignItems: 'center' }, children: [_jsx("span", { style: { width: 88, color: '#555' }, children: r.type }), _jsx("span", { style: { flex: 1 }, children: r.title }), _jsx("code", { style: { color: '#999' }, children: r.id }), _jsx("span", { style: { marginLeft: 'auto' }, children: _jsx("button", { onClick: () => { setNType(r.type); setNParent(r.id); setShowNotionPicker(false); }, children: "Use" }) })] }, r.id))) }), _jsx("div", { style: { display: 'flex', justifyContent: 'flex-end', gap: 8 }, children: _jsx("button", { onClick: () => setShowNotionPicker(false), children: "Close" }) })] }) }))] }));
    }
    // Slack Channel Picker overlay
    const [showSlackPicker, setShowSlackPicker] = useState(false);
    const [slackSearchQ, setSlackSearchQ] = useState('');
    const [slackResults, setSlackResults] = useState([]);
    async function runSlackSearch() {
        try {
            const res = await listSlackChannels(slackToken, slackSearchQ);
            setSlackResults(res.results);
        }
        catch (e) {
            alert('Slack search error: ' + (e?.response?.data?.detail || e.message || e));
        }
    }
    return (_jsxs("div", { style: { fontFamily: 'Inter, system-ui, Arial, sans-serif' }, children: [_jsxs("div", { style: { display: 'flex', gap: 8, padding: 12, borderBottom: '1px solid #eee', alignItems: 'center' }, children: [_jsx("strong", { children: "ChatTools Exporter" }), _jsx("button", { onClick: () => setTab('extract'), children: "Extract" }), _jsx("button", { onClick: () => setTab('settings'), children: "Settings" }), _jsx("button", { onClick: () => setTab('tghelp'), children: "Telegram Help" }), _jsx("button", { onClick: () => setTab('slackhelp'), children: "Slack Help" }), _jsxs("div", { style: { marginLeft: 'auto', color: '#888' }, children: ["API: ", api.defaults.baseURL] })] }), _jsxs("div", { style: { padding: 16 }, children: [tab === 'extract' && _jsx(ExtractTab, {}), tab === 'settings' && _jsx(SettingsTab, {}), tab === 'tghelp' && (_jsx("pre", { style: { whiteSpace: 'pre-wrap' }, children: "Telegram Setup -------------- 1) Create API credentials at my.telegram.org 2) Enter API ID/Hash/Phone in Settings and click Test Login 3) Pick a chat by @username / link / id 4) Use JSONL + Resume for large exports" })), tab === 'slackhelp' && (_jsx("pre", { style: { whiteSpace: 'pre-wrap' }, children: "Slack Setup ----------- 1) Create a Slack app token with channels:read, groups:read, channels:history, groups:history; files:read for media 2) Paste token in Settings and Test Slack 3) Use #name or channel ID for extraction" }))] }), showSlackPicker && (_jsx("div", { style: { position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }, children: _jsxs("div", { style: { background: 'white', padding: 16, borderRadius: 8, width: 600, maxHeight: 520, display: 'flex', flexDirection: 'column', gap: 8 }, children: [_jsx("div", { style: { fontWeight: 600 }, children: "Pick Slack Channel" }), _jsxs("div", { style: { display: 'flex', gap: 8 }, children: [_jsx(TextInput, { value: slackSearchQ, onChange: (e) => setSlackSearchQ(e.target.value), placeholder: "Search by name", style: { width: 360 } }), _jsx("button", { onClick: runSlackSearch, children: "Search" })] }), _jsx("div", { style: { overflow: 'auto', border: '1px solid #eee', flex: 1 }, children: slackResults.map((c) => (_jsxs("div", { style: { padding: 6, borderBottom: '1px solid #f0f0f0', display: 'flex', gap: 8, alignItems: 'center' }, children: [_jsxs("span", { children: ["#", c.name] }), _jsxs("span", { style: { color: '#999' }, children: ["(", c.id, ") ", c.is_private ? 'private' : 'public'] }), _jsxs("span", { style: { marginLeft: 'auto' }, children: [_jsx("button", { onClick: () => { setChat('#' + c.name); setShowSlackPicker(false); }, children: "Use #name" }), _jsx("button", { onClick: () => { setChat(c.id); setShowSlackPicker(false); }, style: { marginLeft: 8 }, children: "Use ID" })] })] }, c.id))) }), _jsx("div", { style: { display: 'flex', justifyContent: 'flex-end', gap: 8 }, children: _jsx("button", { onClick: () => setShowSlackPicker(false), children: "Close" }) })] }) })), false] }));
}
