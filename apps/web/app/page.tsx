import Link from 'next/link';

const features = [
  ['Гонки в реальном времени', 'Печатай один текст с соперниками и двигай машину каждым точным символом.'],
  ['Русский first-class', 'CPM — основной показатель, а правила е/ё настроены отдельно для Casual и Ranked.'],
  ['Без pay-to-win', 'Машины, косметика и подписка не ускоряют тебя. Побеждают пальцы, точность и стабильность.'],
];

export default function HomePage() {
  return (
    <main>
      <nav className="nav shell">
        <Link className="brand" href="/">БУКВОГОН</Link>
        <div className="navLinks">
          <a href="#modes">Режимы</a>
          <Link href="/ranked">Ranked</Link>
          <Link className="pill ghost" href="/pro">Pro · 300 ₽</Link>
        </div>
      </nav>

      <section className="hero shell">
        <div className="eyebrow">РУССКОЯЗЫЧНАЯ TYPING-RACE ИГРА</div>
        <h1>Не просто печатай.<br /><span>Выигрывай гонку.</span></h1>
        <p className="lead">Скорость машины равна твоей скорости печати. Ошибся — потерял темп. Попал в ритм — уходишь вперед.</p>
        <div className="actions">
          <Link className="pill primary" href="/play">Быстрая гонка · бесплатно</Link>
          <Link className="pill secondary" href="/ranked">Посмотреть Ranked</Link>
        </div>
        <div className="track" aria-hidden="true">
          <div className="lane"><span className="car carOne">01</span></div>
          <div className="lane"><span className="car carTwo">07</span></div>
          <div className="lane"><span className="car carThree">13</span></div>
        </div>
      </section>

      <section className="section shell" id="modes">
        <div className="sectionHead">
          <div>
            <div className="eyebrow">ДВА КОНТУРА</div>
            <h2>Free для игры. Pro для рейтинга.</h2>
          </div>
          <p>Мы не режем базовую игру энергией, рекламными попытками или лимитом гонок.</p>
        </div>
        <div className="modeGrid">
          <article className="modeCard">
            <div className="tag">FREE</div>
            <h3>Casual</h3>
            <div className="price">0 ₽ <small>навсегда</small></div>
            <ul>
              <li>Неограниченные обычные гонки</li>
              <li>Комнаты с друзьями</li>
              <li>Тренировка и боты</li>
              <li>XP, достижения и гараж</li>
              <li>Базовая статистика</li>
            </ul>
            <Link className="pill secondary full" href="/play">Играть бесплатно</Link>
          </article>

          <article className="modeCard proCard">
            <div className="tag accent">PRO / RANKED</div>
            <h3>Сезонная лига</h3>
            <div className="price">300 ₽ <small>/ месяц</small></div>
            <ul>
              <li>Ranked matchmaking</li>
              <li>MMR и дивизионы</li>
              <li>Официальный лидерборд</li>
              <li>История рейтинга и percentile</li>
              <li>Расширенная аналитика печати</li>
              <li>Сезонные косметические награды</li>
            </ul>
            <Link className="pill primary full" href="/pro">Открыть Ranked</Link>
          </article>
        </div>
      </section>

      <section className="section shell">
        <div className="featureGrid">
          {features.map(([title, text], index) => (
            <article className="feature" key={title}>
              <span>0{index + 1}</span>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
        </div>
      </section>

      <footer className="footer shell">
        <span>БуквоГон · ранняя разработка</span>
        <span>Скорость покупкой не продается.</span>
      </footer>
    </main>
  );
}
