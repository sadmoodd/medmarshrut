import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api.js';
import { maxBridge } from './maxBridge.js';
import { EmergencyCard, History, QuestionPanel, ResultCard, StartScreen } from './components.jsx';

const STORAGE_KEY = 'medmarshrut.session';

function loadStored() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
  } catch {
    return null;
  }
}

function store(value) {
  try {
    if (value) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* хранилище недоступно: сессия просто не переживёт перезагрузку */
  }
}

export default function App() {
  const [view, setView] = useState(null);
  const [auth, setAuth] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState(null); // сессия MAX, созданная до нажатия «Начать»
  const [greeting, setGreeting] = useState('');
  const [fromMax, setFromMax] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    const launchToken = maxBridge.takeLaunchToken();
    if (launchToken) {
      // JWT живёт 5 минут: обмениваем его на свою сессию сразу при загрузке.
      setFromMax(true);
      setBusy(true);
      api.maxLogin(launchToken)
        .then((data) => {
          const credentials = { id: data.session_id, token: data.session_token };
          store(credentials);
          setAuth(credentials);
          setPending(data);
          setGreeting(data.greeting_name || '');
        })
        .catch((e) => setError(e.message))
        .finally(() => setBusy(false));
      return;
    }
    const saved = loadStored();
    if (!saved) return;
    api.getSession(saved.id, saved.token)
      .then((data) => { setAuth(saved); setView(data); })
      .catch(() => store(null));
  }, []);

  useEffect(() => {
    if (!view) return;
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [view]);

  const run = useCallback(async (action) => {
    setBusy(true);
    setError('');
    try {
      await action();
    } catch (e) {
      if (e.status === 404) { store(null); setView(null); setAuth(null); }
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  const start = () => run(async () => {
    setNotice('');
    if (pending) {
      setView(pending);
      setPending(null);
      return;
    }
    const data = await api.createSession();
    const credentials = { id: data.session_id, token: data.session_token };
    store(credentials);
    setAuth(credentials);
    setView(data);
  });

  const answer = (payload) => run(async () => {
    setView(await api.answer(auth.id, auth.token, { step_id: view.question.id, ...payload }));
  });

  const back = () => run(async () => setView(await api.back(auth.id, auth.token)));

  // Новый опрос — анонимный: токен MAX уже израсходован, для повторного входа откройте бота снова.
  const restart = () => { store(null); setView(null); setAuth(null); setError(''); setPending(null); };

  const removeData = () => run(async () => {
    await api.remove(auth.id, auth.token);
    restart();
    setNotice('Ваши ответы удалены с сервера.');
  });

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">М</span>
          <div>
            <div className="brand-name">МедМаршрут</div>
            <div className="brand-sub">Помощник в выборе врача</div>
          </div>
        </div>
        {view?.status === 'active' && (
          <div className="progress" aria-label="Прогресс опроса">
            <div className="progress-text">
              Вопрос {Math.min(view.progress.answered + 1, view.progress.total)} из {view.progress.total}
            </div>
            <div className="progress-track">
              <div className="progress-bar" style={{ width: `${view.progress.percent}%` }} />
            </div>
          </div>
        )}
      </header>

      <main className="content">
        {!view && (
          <StartScreen
            onStart={start}
            busy={busy}
            notice={notice}
            greeting={greeting}
            fromMax={fromMax}
            loginFailed={fromMax && !pending && !busy && Boolean(error)}
          />
        )}
        {!view && error && <div className="error" role="alert">{error}</div>}

        {view && (
          <>
            <div className="disclaimer">{view.disclaimer_start}</div>
            <History items={view.history} />
            {view.status === 'active' && view.question && (
              <QuestionPanel
                key={view.question.id + view.history.length}
                question={view.question}
                busy={busy}
                canGoBack={view.can_go_back}
                onAnswer={answer}
                onBack={back}
              />
            )}
            {view.status === 'emergency' && (
              <EmergencyCard emergency={view.emergency} onBack={back} onRestart={restart} busy={busy} />
            )}
            {view.status === 'completed' && view.recommendation && (
              <ResultCard
                rec={view.recommendation}
                disclaimer={view.disclaimer_end}
                onBack={back}
                onRestart={restart}
                busy={busy}
              />
            )}
            {error && <div className="error" role="alert">{error}</div>}
            <div className="footer-actions">
              <button type="button" className="link" onClick={removeData} disabled={busy}>
                Удалить мои ответы
              </button>
            </div>
          </>
        )}
        <div ref={bottomRef} />
      </main>
    </div>
  );
}
