import { useState } from 'react';
import { maxBridge } from './maxBridge.js';

export function StartScreen({ onStart, busy, notice, greeting, fromMax, loginFailed }) {
  return (
    <section className="card start">
      {greeting && <div className="greeting">Здравствуйте, {greeting}!</div>}
      <h1>Подскажем, к какому врачу обратиться</h1>
      <p>
        Ответьте на несколько простых вопросов о самочувствии. В конце вы получите
        рекомендацию: к какому специалисту, куда и насколько срочно стоит обратиться.
      </p>
      <ul className="facts">
        <li>Около 3 минут, 12–14 вопросов</li>
        <li>Имя, телефон и адрес не нужны</li>
        <li>Ответы хранятся в зашифрованном виде и удаляются через 24 часа</li>
      </ul>
      <div className="notice-important">
        <strong>Важно.</strong> Сервис не ставит диагноз и не заменяет врача. Если состояние
        тяжёлое, сразу звоните 103 или 112.
      </div>
      {!fromMax && (
        <div className="notice-info">
          Чтобы войти со своим профилем, откройте сервис из бота MAX. Без входа опрос
          работает анонимно.
        </div>
      )}
      {notice && <div className="notice">{notice}</div>}
      <button type="button" className="btn primary wide" onClick={onStart} disabled={busy}>
        {busy && fromMax ? 'Вход через MAX…' : loginFailed ? 'Продолжить без входа' : 'Начать'}
      </button>
    </section>
  );
}

export function History({ items }) {
  return (
    <div className="history">
      {items.map((item) => (
        <div key={item.step_id} className="exchange">
          <div className="msg bot">{item.question}</div>
          <div className="msg user">{item.answer}</div>
        </div>
      ))}
    </div>
  );
}

export function QuestionPanel({ question, busy, canGoBack, onAnswer, onBack }) {
  const [selected, setSelected] = useState([]);
  const [text, setText] = useState('');
  const multi = question.type === 'multi';

  const toggle = (option) => {
    setSelected((current) => {
      if (current.includes(option.id)) return current.filter((id) => id !== option.id);
      if (option.exclusive) return [option.id];
      const exclusiveIds = question.options.filter((o) => o.exclusive).map((o) => o.id);
      return [...current.filter((id) => !exclusiveIds.includes(id)), option.id];
    });
  };

  const submitText = (event) => {
    event.preventDefault();
    if (text.trim()) onAnswer({ option_ids: multi ? selected : [], text: text.trim() });
  };

  return (
    <section className="question">
      <div className="msg bot current">
        {question.text}
        {question.hint && <div className="hint">{question.hint}</div>}
      </div>

      <div className={multi ? 'options checklist' : 'options'}>
        {question.options.map((option) => (
          multi ? (
            <label key={option.id} className={selected.includes(option.id) ? 'check selected' : 'check'}>
              <input
                type="checkbox"
                checked={selected.includes(option.id)}
                onChange={() => toggle(option)}
                disabled={busy}
              />
              <span>{option.label}</span>
            </label>
          ) : (
            <button
              key={option.id}
              type="button"
              className="btn option"
              onClick={() => onAnswer({ option_ids: [option.id] })}
              disabled={busy}
            >
              {option.label}
            </button>
          )
        ))}
      </div>

      {question.allow_text && (
        <form className="free-text" onSubmit={submitText}>
          <textarea
            value={text}
            maxLength={500}
            rows={2}
            placeholder={question.text_placeholder || 'Опишите своими словами'}
            onChange={(e) => setText(e.target.value)}
            disabled={busy}
          />
          <button type="submit" className="btn secondary" disabled={busy || !text.trim()}>
            Отправить
          </button>
        </form>
      )}

      <div className="actions">
        <button type="button" className="btn ghost" onClick={onBack} disabled={busy || !canGoBack}>
          Назад
        </button>
        <div className="actions-right">
          {question.optional && (
            <button type="button" className="btn ghost" onClick={() => onAnswer({ skip: true })} disabled={busy}>
              Пропустить
            </button>
          )}
          {multi && (
            <button
              type="button"
              className="btn primary"
              onClick={() => onAnswer({ option_ids: selected, text: text.trim() || null })}
              disabled={busy || (selected.length === 0 && !text.trim())}
            >
              Далее
            </button>
          )}
        </div>
      </div>
    </section>
  );
}

export function EmergencyCard({ emergency, onBack, onRestart, busy }) {
  return (
    <section className="card emergency" role="alert">
      <div className="emergency-label">Требуется экстренная помощь</div>
      <h2>{emergency.message}</h2>
      <ul className="flags">
        {emergency.flags.map((flag) => (
          <li key={flag.code}>
            <strong>{flag.title}.</strong> {flag.explanation}
          </li>
        ))}
      </ul>
      <ul className="advice">
        {emergency.advice.map((line) => <li key={line}>{line}</li>)}
      </ul>
      <div className="call-buttons">
        <button type="button" className="btn danger" onClick={() => maxBridge.openPhone('103')}>Позвонить 103</button>
        <button type="button" className="btn danger outline" onClick={() => maxBridge.openPhone('112')}>Позвонить 112</button>
      </div>
      <div className="actions">
        <button type="button" className="btn ghost" onClick={onBack} disabled={busy}>
          Я ошибся в ответе — вернуться
        </button>
        <button type="button" className="btn ghost" onClick={onRestart}>Начать заново</button>
      </div>
    </section>
  );
}

const URGENCY_CLASS = { urgent: 'badge urgent', planned: 'badge planned', self_care: 'badge self', emergency: 'badge emergency' };

export function ResultCard({ rec, disclaimer, onBack, onRestart, busy }) {
  return (
    <section className="card result">
      <div className="result-head">
        <div className="result-label">Рекомендация</div>
        <span className={URGENCY_CLASS[rec.urgency]}>{rec.urgency_label}</span>
      </div>
      <dl className="result-grid">
        <dt>Специалист</dt>
        <dd>{rec.specialty}</dd>
        <dt>Куда обратиться</dt>
        <dd>
          {rec.care_place_label}
          {rec.alternatives.length > 0 && <div className="alt">Также подойдёт: {rec.alternatives.join(', ')}</div>}
        </dd>
      </dl>
      <h3>Почему такая рекомендация</h3>
      <ul className="rationale">
        {rec.rationale.map((line) => <li key={line}>{line}</li>)}
      </ul>
      {rec.advice.length > 0 && (
        <>
          <h3>Что сделать</h3>
          <ul className="advice">
            {rec.advice.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </>
      )}
      <div className="notice-important">
        Рекомендация не является диагнозом. {disclaimer}
      </div>
      <div className="actions">
        <button type="button" className="btn ghost" onClick={onBack} disabled={busy}>Изменить последний ответ</button>
        <button type="button" className="btn primary" onClick={onRestart}>Новый опрос</button>
      </div>
    </section>
  );
}
