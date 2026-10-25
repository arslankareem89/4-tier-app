import React, { useEffect, useState } from 'react';

// Local development uses FastAPI on port 8000.
// Production uses the same CloudFront domain for frontend and API.
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);
const API_URL = LOCAL_HOSTS.has(window.location.hostname)
  ? 'http://localhost:8000'
  : '';

async function request(path, token, options = {}) {
  const headers = { ...options.headers };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const response = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    const problem = await response.json().catch(() => ({}));
    throw new Error(problem.detail || `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

function App() {
  const [token, setToken] = useState(() => localStorage.getItem('task_token'));
  const [user, setUser] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [uploads, setUploads] = useState([]);
  const [isRegistering, setIsRegistering] = useState(false);
  const [isLoading, setIsLoading] = useState(Boolean(token));
  const [isSaving, setIsSaving] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [editingTask, setEditingTask] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) {
      setIsLoading(false);
      return undefined;
    }

    let active = true;
    setIsLoading(true);
    Promise.all([
      request('/auth/me', token),
      request('/tasks', token),
      request('/uploads', token),
    ])
      .then(([currentUser, currentTasks, currentUploads]) => {
        if (!active) return;
        setUser(currentUser);
        setTasks(currentTasks);
        setUploads(currentUploads);
        setError('');
      })
      .catch((requestError) => {
        if (!active) return;
        localStorage.removeItem('task_token');
        setToken(null);
        setUser(null);
        setError(requestError.message);
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [token]);

  async function refreshTasks() {
    setTasks(await request('/tasks', token));
  }

  async function refreshUploads() {
    setUploads(await request('/uploads', token));
  }

  async function handleAuthSubmit(event) {
    event.preventDefault();
    setIsSaving(true);
    setError('');
    try {
      const result = await request(`/auth/${isRegistering ? 'register' : 'login'}`, null, {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      });
      localStorage.setItem('task_token', result.access_token);
      setToken(result.access_token);
      setPassword('');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTaskSubmit(event) {
    event.preventDefault();
    setIsSaving(true);
    setError('');
    const method = editingTask ? 'PATCH' : 'POST';
    const path = editingTask ? `/tasks/${editingTask.id}` : '/tasks';
    try {
      await request(path, token, {
        method,
        body: JSON.stringify({ title, description }),
      });
      setTitle('');
      setDescription('');
      setEditingTask(null);
      await refreshTasks();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSaving(false);
    }
  }

  function startEditing(task) {
    setEditingTask(task);
    setTitle(task.title);
    setDescription(task.description);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function cancelEditing() {
    setEditingTask(null);
    setTitle('');
    setDescription('');
  }

  async function updateTask(task, changes) {
    setError('');
    try {
      await request(`/tasks/${task.id}`, token, {
        method: 'PATCH',
        body: JSON.stringify(changes),
      });
      await refreshTasks();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function deleteTask(task) {
    setError('');
    try {
      await request(`/tasks/${task.id}`, token, { method: 'DELETE' });
      await refreshTasks();
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function handleUpload(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const file = form.elements.file.files[0];
    if (!file) return;
    setIsSaving(true);
    setError('');
    const formData = new FormData();
    formData.append('file', file);
    try {
      await request('/uploads', token, { method: 'POST', body: formData });
      form.reset();
      await refreshUploads();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setIsSaving(false);
    }
  }

  async function downloadUpload(upload) {
    setError('');
    try {
      const response = await fetch(`${API_URL}/uploads/${upload.id}/file`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok) throw new Error('Could not download this file');
      const fileUrl = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = fileUrl;
      link.download = upload.original_name;
      link.click();
      URL.revokeObjectURL(fileUrl);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  function signOut() {
    localStorage.removeItem('task_token');
    setToken(null);
    setUser(null);
    setTasks([]);
    setUploads([]);
    cancelEditing();
  }

  if (!token) {
    return (
      <main className="auth-shell">
        <section className="auth-panel" aria-labelledby="auth-title">
          <p className="eyebrow">FIELDNOTES / TASKS</p>
          <h1 id="auth-title">Make room for the work.</h1>
          <p className="auth-copy">A clear place to track what is moving and what comes next.</p>
          {error && <p className="notice" role="alert">{error}</p>}
          <form className="auth-form" onSubmit={handleAuthSubmit}>
            <label htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete={isRegistering ? 'new-password' : 'current-password'} minLength="8" value={password} onChange={(event) => setPassword(event.target.value)} required />
            {isRegistering && <p className="field-hint">Use at least 8 characters.</p>}
            <button className="button button-primary auth-submit" type="submit" disabled={isSaving}>
              {isSaving ? 'Please wait…' : isRegistering ? 'Create account' : 'Sign in'}
            </button>
          </form>
          <button className="text-button auth-switch" type="button" onClick={() => { setIsRegistering(!isRegistering); setError(''); }}>
            {isRegistering ? 'Already have an account? Sign in' : 'New here? Create an account'}
          </button>
        </section>
        <aside className="auth-note"><span>01</span><p>Small steps, clearly seen.</p></aside>
      </main>
    );
  }

  if (isLoading || !user) {
    return <main className="loading-screen"><span className="loading-mark" />Loading your workspace</main>;
  }

  const completedCount = tasks.filter((task) => task.status === 'COMPLETED').length;

  return (
    <main className="workspace">
      <header className="topbar">
        <a className="wordmark" href="#top" aria-label="Fieldnotes home"><span className="wordmark-mark">F</span> fieldnotes</a>
        <div className="account-area"><span className="account-email">{user.email}</span><button className="button button-quiet" type="button" onClick={signOut}>Sign out</button></div>
      </header>

      <section className="page-heading" id="top">
        <div>
          <p className="eyebrow">YOUR WORKSPACE</p>
          <h1>Good work, in motion.</h1>
          <p className="heading-copy">Keep the next step close.</p>
        </div>
        <div className="progress-stamp"><strong>{completedCount}<span> / </span>{tasks.length}</strong><small>tasks complete</small></div>
      </section>

      {error && <p className="notice workspace-notice" role="alert">{error}</p>}

      <div className="workspace-grid">
        <section className="task-column" aria-labelledby="tasks-title">
          <div className="section-heading">
            <div><p className="eyebrow">THE LIST</p><h2 id="tasks-title">Tasks <span className="count">{tasks.length}</span></h2></div>
          </div>

          <form className="task-form" onSubmit={handleTaskSubmit}>
            <div className="form-topline"><h3>{editingTask ? 'Edit task' : 'Add a task'}</h3><span className="form-index">{editingTask ? 'EDITING' : 'NEW ITEM'}</span></div>
            <label className="visually-hidden" htmlFor="task-title">Task title</label>
            <input id="task-title" className="title-input" type="text" placeholder="What needs doing?" maxLength="200" value={title} onChange={(event) => setTitle(event.target.value)} required />
            <label className="visually-hidden" htmlFor="task-description">Task description</label>
            <textarea id="task-description" placeholder="Add a note or useful detail…" maxLength="10000" rows="3" value={description} onChange={(event) => setDescription(event.target.value)} />
            <div className="form-actions">
              {editingTask && <button className="button button-quiet" type="button" onClick={cancelEditing}>Cancel</button>}
              <button className="button button-primary" type="submit" disabled={isSaving}>{editingTask ? 'Save changes' : 'Add task'} <span aria-hidden="true">↗</span></button>
            </div>
          </form>

          {tasks.length === 0 ? (
            <div className="empty-state"><span className="empty-mark">+</span><h3>A fresh page.</h3><p>Add a task above to start your list.</p></div>
          ) : (
            <ul className="task-list">
              {tasks.map((task, index) => (
                <li className={`task-item ${task.status === 'COMPLETED' ? 'is-complete' : ''}`} key={task.id}>
                  <button className="task-check" type="button" aria-label={task.status === 'COMPLETED' ? 'Mark task pending' : 'Mark task complete'} onClick={() => updateTask(task, { status: task.status === 'COMPLETED' ? 'PENDING' : 'COMPLETED' })}>
                    {task.status === 'COMPLETED' ? '✓' : String(index + 1).padStart(2, '0')}
                  </button>
                  <div className="task-content"><div className="task-title-row"><h3>{task.title}</h3><span className={`status status-${task.status.toLowerCase().replace('_', '-')}`}>{task.status.replace('_', ' ')}</span></div>{task.description && <p>{task.description}</p>}</div>
                  <div className="task-actions"><button className="icon-action" type="button" aria-label={`Edit ${task.title}`} title="Edit task" onClick={() => startEditing(task)}>Edit</button><button className="icon-action delete-action" type="button" aria-label={`Delete ${task.title}`} title="Delete task" onClick={() => deleteTask(task)}>Delete</button></div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <aside className="side-column">
          <section className="upload-section" aria-labelledby="files-title">
            <div className="section-heading"><div><p className="eyebrow">KEEP CLOSE</p><h2 id="files-title">Files <span className="count">{uploads.length}</span></h2></div></div>
            <form className="upload-form" onSubmit={handleUpload}>
              <label className="file-picker"><span className="upload-symbol" aria-hidden="true">↑</span><span><strong>Choose a file</strong><small>Stored in your workspace</small></span><input name="file" type="file" required /></label>
              <button className="button button-outline" type="submit" disabled={isSaving}>Upload file</button>
            </form>
            {uploads.length > 0 ? (
              <ul className="file-list">{uploads.map((upload) => (
                <li key={upload.id} className="file-item"><span className="file-type">{upload.original_name.split('.').pop().slice(0, 4).toUpperCase()}</span><span className="file-detail"><strong>{upload.original_name}</strong><small>{upload.processing_status === 'complete' ? `${(upload.size / 1024).toFixed(1)} KB · verified` : 'Processing…'}</small></span><button className="icon-action" type="button" onClick={() => downloadUpload(upload)} aria-label={`Download ${upload.original_name}`} title="Download file">↓</button></li>
              ))}</ul>
            ) : <p className="files-empty">Your uploaded files will appear here.</p>}
          </section>
          <div className="workspace-footnote"><span className="footnote-rule" /><p>Progress is a practice.<br />Keep showing up.</p><span className="footnote-number">FN—01</span></div>
        </aside>
      </div>
    </main>
  );
}

export default App;