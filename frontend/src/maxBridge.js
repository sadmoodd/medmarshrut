// Связь с мини-приложением MAX.
//
// Мини-приложение открывает наш URL с query-параметром `token` — JWT пользователя,
// который живёт 5 минут. Мы сразу забираем его из адреса, убираем из адресной строки
// (чтобы он не остался в истории браузера) и передаём на наш бэкенд. В core браузер
// не ходит: сервисный токен команды хранится только на сервере.

let consumed = false;

export const maxBridge = {
  /** Забирает token из URL ровно один раз и стирает его из адресной строки. */
  takeLaunchToken() {
    if (consumed) return null;
    consumed = true;
    const url = new URL(window.location.href);
    const token = url.searchParams.get('token');
    if (token) {
      url.searchParams.delete('token');
      window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    }
    return token;
  },

  /** Открыть телефонный номер (вызов скорой). */
  openPhone(number) {
    window.location.href = `tel:${number}`;
  },
};
