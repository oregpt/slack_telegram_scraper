import React, { useEffect, useMemo, useState } from 'react'
import {
  api,
  getTask,
  loadConfig,
  saveConfig,
  startSlackExport,
  startTelegramExport,
  testNotion,
  testSlack,
  tgLoginComplete,
  tgLoginStart,
  TaskStatus,
  searchNotion,
  listSlackChannels,
} from './api'

type Cfg = any

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 8, padding: 12, marginBottom: 16 }}>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  )
}

function Row({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>{children}</div>
}

function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} style={{ ...(props.style || {}), padding: '6px 8px', width: props.style?.width || 280 }} />
}

function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} style={{ ...(props.style || {}), padding: '6px 8px', width: props.style?.width || 280 }} />
}

export default function App() {
  const [cfg, setCfg] = useState<Cfg | null>(null)
  const [tab, setTab] = useState<'extract' | 'settings' | 'tghelp' | 'slackhelp'>('extract')
  const [busy, setBusy] = useState(false)
  const [task, setTask] = useState<TaskStatus | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)

  useEffect(() => {
    loadConfig().then(setCfg)
  }, [])

  useEffect(() => {
    if (!taskId) return
    setTask(null)
    const t = setInterval(async () => {
      try {
        const st = await getTask(taskId)
        setTask(st)
        if (st.status !== 'running') clearInterval(t)
      } catch (e) {
        clearInterval(t)
      }
    }, 800)
    return () => clearInterval(t)
  }, [taskId])

  if (!cfg) return <div style={{ padding: 16 }}>Loading...</div>

  const dfl = cfg.defaults || {}

  const [tgApiId, setTgApiId] = useState<string>(cfg.telegram?.api_id || '')
  const [tgApiHash, setTgApiHash] = useState<string>(cfg.telegram?.api_hash || '')
  const [tgPhone, setTgPhone] = useState<string>(cfg.telegram?.phone || '')
  const [tgSession, setTgSession] = useState<string>(cfg.telegram?.session || '')

  const [slackToken, setSlackToken] = useState<string>(cfg.slack?.token || '')

  const [dest, setDest] = useState<string>(dfl.destination || 'Folder (local)')
  const [format, setFormat] = useState<string>(dfl.format || 'jsonl')
  const [reverse, setReverse] = useState<boolean>(!!dfl.reverse)
  const [resume, setResume] = useState<boolean>(!!dfl.resume)
  const [only, setOnly] = useState<string>(dfl.only || 'all')
  const [limit, setLimit] = useState<string>('')
  const [minDate, setMinDate] = useState('')
  const [maxDate, setMaxDate] = useState('')
  const [users, setUsers] = useState('')
  const [keywords, setKeywords] = useState('')
  const [chat, setChat] = useState('')
  const [media, setMedia] = useState(false)
  const [outFolder, setOutFolder] = useState<string>(dfl.last_output_folder || '')
  const [filename, setFilename] = useState<string>(dfl.filename || 'messages.jsonl')

  const notionDests: any[] = cfg.notion?.destinations || []
  const notionNames = notionDests.map((d) => d.name)
  const [notionSel, setNotionSel] = useState<string>(notionNames[0] || '')
  const selectedNotion = useMemo(() => notionDests.find((d) => d.name === notionSel), [notionSel, notionDests])
  const [notionMode, setNotionMode] = useState<string>(dfl.notion_mode || 'per_message')

  const fsOutPath = `${outFolder.replace(/\\+$/,'')}/${filename}`

  async function handleSaveSettings() {
    const next = {
      ...cfg,
      telegram: { api_id: tgApiId, api_hash: tgApiHash, phone: tgPhone, session: tgSession || undefined },
      slack: { token: slackToken },
      defaults: { ...cfg.defaults, format, reverse, resume, destination: dest, only, last_output_folder: outFolder, filename, notion_mode: notionMode },
    }
    await saveConfig(next)
    setCfg(next)
    alert('Settings saved')
  }

  async function doTgTestLogin() {
    setBusy(true)
    try {
      await tgLoginStart({ api_id: Number(tgApiId), api_hash: tgApiHash, phone: tgPhone, session: tgSession || undefined })
      const code = window.prompt('Enter Telegram login code:') || ''
      if (!code) return
      const password = window.prompt('If you have 2FA password, enter it (or leave blank):') || undefined
      await tgLoginComplete({ api_id: Number(tgApiId), api_hash: tgApiHash, phone: tgPhone, code, password, session: tgSession || undefined })
      alert('Telegram login OK. Session saved.')
    } catch (e: any) {
      alert('Login failed: ' + (e?.response?.data?.detail || e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function doTestSlack() {
    setBusy(true)
    try {
      const res = await testSlack(slackToken)
      alert(res.message)
    } catch (e: any) {
      alert('Slack error: ' + (e?.response?.data?.detail || e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function doTestNotion() {
    const nd = selectedNotion
    if (!nd) return alert('Pick a Notion destination in Settings')
    setBusy(true)
    try {
      const res = await testNotion(nd.api_key, nd.type, nd.parent_id)
      alert(res.message)
    } catch (e: any) {
      alert('Notion error: ' + (e?.response?.data?.detail || e.message || e))
    } finally {
      setBusy(false)
    }
  }

  async function doExtract() {
    setBusy(true)
    setTaskId(null)
    setTask(null)
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
      }
      let start
      if ((cfg.app || 'Telegram').startsWith('Telegram')) {
        const payload: any = {
          api_id: Number(tgApiId),
          api_hash: tgApiHash,
          session: tgSession || undefined,
          chat,
          media_dir: media ? (outFolder + '/media') : undefined,
          ...common,
        }
        if (dest.startsWith('Notion') && selectedNotion) {
          payload.notion_api_key = selectedNotion.api_key
          payload.notion_dest_type = selectedNotion.type
          payload.notion_parent_id = selectedNotion.parent_id
          payload.notion_mode = notionMode
        } else {
          payload.out = fsOutPath
          payload.format = format
        }
        start = startTelegramExport(payload)
      } else {
        const payload: any = {
          token: slackToken,
          channel: chat,
          media_dir: media ? (outFolder + '/media') : undefined,
          ...common,
        }
        if (dest.startsWith('Notion') && selectedNotion) {
          payload.notion_api_key = selectedNotion.api_key
          payload.notion_dest_type = selectedNotion.type
          payload.notion_parent_id = selectedNotion.parent_id
          payload.notion_mode = notionMode
        } else {
          payload.out = fsOutPath
          payload.format = format
        }
        start = startSlackExport(payload)
      }
      const { task_id } = await start!
      setTaskId(task_id)
    } catch (e: any) {
      alert('Start error: ' + (e?.response?.data?.detail || e.message || e))
    } finally {
      setBusy(false)
    }
  }

  function ExtractTab() {
    const appOptions = ['Telegram', 'Slack (coming soon)', 'Teams (coming soon)']
    return (
      <div>
        <Section title="Extract">
          <Row>
            <label>Chat Application:</label>
            <Select value={cfg.app || 'Telegram'} onChange={(e) => setCfg({ ...cfg, app: e.currentTarget.value })}>
              {appOptions.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </Select>
          </Row>
          <Row>
            <label>Chat / Channel:</label>
            <TextInput value={chat} onChange={(e) => setChat(e.target.value)} placeholder="@username / link / id or #name" />
            {(cfg.app || 'Telegram').startsWith('Slack') && (
              <button onClick={() => setShowSlackPicker(true)}>Pick Channel…</button>
            )}
          </Row>
          <Row>
            <label>Min Date (YYYY-MM-DD):</label>
            <TextInput value={minDate} onChange={(e) => setMinDate(e.target.value)} style={{ width: 150 }} />
            <label>Max Date (YYYY-MM-DD):</label>
            <TextInput value={maxDate} onChange={(e) => setMaxDate(e.target.value)} style={{ width: 150 }} />
          </Row>
          <Row>
            <label>Content:</label>
            <Select value={only} onChange={(e) => setOnly(e.currentTarget.value)} style={{ width: 160 }}>
              <option value="all">All</option>
              <option value="media">Only media</option>
              <option value="text">Only text</option>
            </Select>
            <label>Format:</label>
            <Select value={format} onChange={(e) => setFormat(e.currentTarget.value)} style={{ width: 120 }}>
              <option value="jsonl">jsonl</option>
              <option value="csv">csv</option>
            </Select>
            <label>Limit:</label>
            <TextInput value={limit} onChange={(e) => setLimit(e.target.value)} style={{ width: 100 }} />
          </Row>
          <Row>
            <label>Users (comma ids/usernames):</label>
            <TextInput value={users} onChange={(e) => setUsers(e.target.value)} style={{ width: 420 }} />
          </Row>
          <Row>
            <label>Keywords (comma):</label>
            <TextInput value={keywords} onChange={(e) => setKeywords(e.target.value)} style={{ width: 420 }} />
          </Row>
          <Row>
            <label>
              <input type="checkbox" checked={reverse} onChange={(e) => setReverse(e.target.checked)} /> Oldest → newest
            </label>
            <label>
              <input type="checkbox" checked={resume} onChange={(e) => setResume(e.target.checked)} /> Resume (JSONL)
            </label>
            <label>
              <input type="checkbox" checked={media} onChange={(e) => setMedia(e.target.checked)} /> Download media
            </label>
          </Row>

          <Row>
            <label>Destination:</label>
            <Select value={dest} onChange={(e) => setDest(e.currentTarget.value)} style={{ width: 220 }}>
              <option>Folder (local)</option>
              <option>Notion (saved destination)</option>
            </Select>
          </Row>

          {dest.startsWith('Folder') ? (
            <>
              <Row>
                <label>Output folder:</label>
                <TextInput value={outFolder} onChange={(e) => setOutFolder(e.target.value)} style={{ width: 420 }} />
              </Row>
              <Row>
                <label>Filename:</label>
                <TextInput value={filename} onChange={(e) => setFilename(e.target.value)} style={{ width: 260 }} />
              </Row>
            </>
          ) : (
            <>
              <Row>
                <label>Notion destination:</label>
                <Select value={notionSel} onChange={(e) => setNotionSel(e.currentTarget.value)} style={{ width: 320 }}>
                  {notionNames.length === 0 && <option>(none saved)</option>}
                  {notionNames.map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
                <label>Mode:</label>
                <Select value={notionMode} onChange={(e) => setNotionMode(e.currentTarget.value)} style={{ width: 160 }}>
                  <option value="per_message">per_message</option>
                  <option value="group_by_day">group_by_day</option>
                </Select>
                <button onClick={doTestNotion}>Test Notion</button>
              </Row>
            </>
          )}

          <Row>
            <button disabled={busy} onClick={doExtract}>
              {busy ? 'Starting…' : 'Extract'}
            </button>
          </Row>
        </Section>

        {taskId && (
          <Section title={`Task ${taskId}`}> 
            <Row>
              <div>Status: {task?.status || 'running'}</div>
              {task?.result && <div>Result: {JSON.stringify(task.result)}</div>}
              {task?.error && <div style={{ color: 'red' }}>Error: {task.error}</div>}
            </Row>
            <div style={{ maxHeight: 300, overflow: 'auto', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 12, background: '#fafafa', padding: 8, border: '1px solid #eee' }}>
              {(task?.logs || []).map((l, i) => (
                <div key={i}>{l}</div>
              ))}
            </div>
          </Section>
        )}
      </div>
    )
  }

  function SettingsTab() {
    const [showNotionPicker, setShowNotionPicker] = useState(false)
    const [searchQ, setSearchQ] = useState('')
    const [searchResults, setSearchResults] = useState<any[]>([])
    const [nName, setNName] = useState('')
    const [nKey, setNKey] = useState('')
    const [nType, setNType] = useState<'Database' | 'Page'>('Database' as any)
    const [nParent, setNParent] = useState('')

    function addOrUpdateNotion() {
      const dests = [...(cfg.notion?.destinations || [])]
      const idx = dests.findIndex((d: any) => d.name === nName)
      const rec = { name: nName, api_key: nKey, type: nType, parent_id: nParent }
      if (idx >= 0) dests[idx] = rec
      else dests.push(rec)
      const next = { ...cfg, notion: { destinations: dests } }
      setCfg(next)
    }

    async function openNotionPicker() {
      if (!nKey) return alert('Enter Notion API Key first')
      setSearchQ('')
      setSearchResults([])
      setShowNotionPicker(true)
    }

    async function runNotionSearch() {
      if (!nKey) return alert('Enter Notion API Key first')
      const res = await searchNotion(nKey, searchQ || '')
      setSearchResults(res.results)
    }

    return (
      <div>
        <Section title="Telegram">
          <Row>
            <label>API ID:</label>
            <TextInput value={tgApiId} onChange={(e) => setTgApiId(e.target.value)} />
            <label>API Hash:</label>
            <TextInput value={tgApiHash} onChange={(e) => setTgApiHash(e.target.value)} />
          </Row>
          <Row>
            <label>Phone:</label>
            <TextInput value={tgPhone} onChange={(e) => setTgPhone(e.target.value)} />
            <label>Session (optional):</label>
            <TextInput value={tgSession} onChange={(e) => setTgSession(e.target.value)} />
          </Row>
          <Row>
            <button disabled={busy} onClick={doTgTestLogin}>Test Login</button>
          </Row>
        </Section>

        <Section title="Slack">
          <Row>
            <label>Token:</label>
            <TextInput value={slackToken} onChange={(e) => setSlackToken(e.target.value)} style={{ width: 420 }} />
            <button disabled={busy} onClick={doTestSlack}>Test Slack</button>
          </Row>
        </Section>

        <Section title="Notion Destinations">
          <Row>
            <label>Name:</label>
            <TextInput value={nName} onChange={(e) => setNName(e.target.value)} />
            <label>API Key:</label>
            <TextInput value={nKey} onChange={(e) => setNKey(e.target.value)} style={{ width: 340 }} />
          </Row>
          <Row>
            <label>Type:</label>
            <Select value={nType} onChange={(e) => setNType(e.currentTarget.value as any)} style={{ width: 160 }}>
              <option>Database</option>
              <option>Page</option>
            </Select>
            <label>Parent ID:</label>
            <TextInput value={nParent} onChange={(e) => setNParent(e.target.value)} style={{ width: 360 }} />
            <button onClick={openNotionPicker}>Pick Parent…</button>
            <button onClick={addOrUpdateNotion}>Save Destination</button>
          </Row>
          <div>
            Saved: {notionDests.length ? notionDests.map((d: any) => d.name).join(', ') : '(none)'}
          </div>
        </Section>

        <Row>
          <button onClick={handleSaveSettings}>Save Settings</button>
        </Row>
        {showNotionPicker && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ background: 'white', padding: 16, borderRadius: 8, width: 720, maxHeight: 560, display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div style={{ fontWeight: 600 }}>Pick Notion Parent</div>
              <div style={{ display: 'flex', gap: 8 }}>
                <TextInput value={searchQ} onChange={(e) => setSearchQ(e.target.value)} placeholder="Search pages/databases by title" style={{ width: 480 }} />
                <button onClick={runNotionSearch}>Search</button>
              </div>
              <div style={{ overflow: 'auto', border: '1px solid #eee', flex: 1 }}>
                {searchResults.map((r: any) => (
                  <div key={r.id} style={{ padding: 6, borderBottom: '1px solid #f0f0f0', display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ width: 88, color: '#555' }}>{r.type}</span>
                    <span style={{ flex: 1 }}>{r.title}</span>
                    <code style={{ color: '#999' }}>{r.id}</code>
                    <span style={{ marginLeft: 'auto' }}>
                      <button onClick={() => { setNType(r.type); setNParent(r.id); setShowNotionPicker(false) }}>Use</button>
                    </span>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button onClick={() => setShowNotionPicker(false)}>Close</button>
              </div>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Slack Channel Picker overlay
  const [showSlackPicker, setShowSlackPicker] = useState(false)
  const [slackSearchQ, setSlackSearchQ] = useState('')
  const [slackResults, setSlackResults] = useState<{ id: string; name: string; is_private: boolean }[]>([])
  async function runSlackSearch() {
    try {
      const res = await listSlackChannels(slackToken, slackSearchQ)
      setSlackResults(res.results)
    } catch (e: any) {
      alert('Slack search error: ' + (e?.response?.data?.detail || e.message || e))
    }
  }

  return (
    <div style={{ fontFamily: 'Inter, system-ui, Arial, sans-serif' }}>
      <div style={{ display: 'flex', gap: 8, padding: 12, borderBottom: '1px solid #eee', alignItems: 'center' }}>
        <strong>ChatTools Exporter</strong>
        <button onClick={() => setTab('extract')}>Extract</button>
        <button onClick={() => setTab('settings')}>Settings</button>
        <button onClick={() => setTab('tghelp')}>Telegram Help</button>
        <button onClick={() => setTab('slackhelp')}>Slack Help</button>
        <div style={{ marginLeft: 'auto', color: '#888' }}>API: {api.defaults.baseURL}</div>
      </div>
      <div style={{ padding: 16 }}>
        {tab === 'extract' && <ExtractTab />}
        {tab === 'settings' && <SettingsTab />}
        {tab === 'tghelp' && (
          <pre style={{ whiteSpace: 'pre-wrap' }}>
Telegram Setup
--------------
1) Create API credentials at my.telegram.org
2) Enter API ID/Hash/Phone in Settings and click Test Login
3) Pick a chat by @username / link / id
4) Use JSONL + Resume for large exports
          </pre>
        )}
        {tab === 'slackhelp' && (
          <pre style={{ whiteSpace: 'pre-wrap' }}>
Slack Setup
-----------
1) Create a Slack app token with channels:read, groups:read, channels:history, groups:history; files:read for media
2) Paste token in Settings and Test Slack
3) Use #name or channel ID for extraction
          </pre>
        )}
      </div>

      {showSlackPicker && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.35)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ background: 'white', padding: 16, borderRadius: 8, width: 600, maxHeight: 520, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ fontWeight: 600 }}>Pick Slack Channel</div>
            <div style={{ display: 'flex', gap: 8 }}>
              <TextInput value={slackSearchQ} onChange={(e) => setSlackSearchQ(e.target.value)} placeholder="Search by name" style={{ width: 360 }} />
              <button onClick={runSlackSearch}>Search</button>
            </div>
            <div style={{ overflow: 'auto', border: '1px solid #eee', flex: 1 }}>
              {slackResults.map((c) => (
                <div key={c.id} style={{ padding: 6, borderBottom: '1px solid #f0f0f0', display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span>#{c.name}</span>
                  <span style={{ color: '#999' }}>({c.id}) {c.is_private ? 'private' : 'public'}</span>
                  <span style={{ marginLeft: 'auto' }}>
                    <button onClick={() => { setChat('#' + c.name); setShowSlackPicker(false) }}>Use #name</button>
                    <button onClick={() => { setChat(c.id); setShowSlackPicker(false) }} style={{ marginLeft: 8 }}>Use ID</button>
                  </span>
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <button onClick={() => setShowSlackPicker(false)}>Close</button>
            </div>
          </div>
        </div>
      )}

      {/* Notion Parent Picker overlay (in Settings) */}
      {/* We show it globally and let SettingsTab control fields */}
      {false}
    </div>
  )
}
