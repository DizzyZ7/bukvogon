import Link from 'next/link';

import { RaceScene } from '../../components/race/RaceScene';

export default function PlayPage() {
  return (
    <main className="playPage">
      <nav className="nav shell">
        <Link className="brand" href="/">БУКВОГОН</Link>
        <div className="navLinks">
          <Link href="/">Главная</Link>
          <Link href="/ranked">Ranked</Link>
          <Link className="pill ghost" href="/pro">Pro · 300 ₽</Link>
        </div>
      </nav>

      <section className="playHero shell">
        <div className="eyebrow">CASUAL · БЕСПЛАТНО</div>
        <h1>Выбери, кто<br /><span>помчится по строке.</span></h1>
        <p className="lead narrow">
          Машинки, котики, гусенички или самолеты — это только твой визуальный слой. Скорость и позиция соперников остаются одинаковыми в любом оформлении.
        </p>
      </section>

      <div className="shell">
        <RaceScene />
      </div>

      <section className="section shell compact playNextStep">
        <div>
          <div className="eyebrow">СЛЕДУЮЩИЙ СЛОЙ</div>
          <h2>Дальше подключим настоящий realtime.</h2>
          <p className="muted">
            Эта сцена уже построена так, чтобы статический preview-state позже без переделки визуальных тем заменить WebSocket-состоянием реального матча.
          </p>
        </div>
        <Link className="pill primary" href="/ranked">Посмотреть Ranked</Link>
      </section>
    </main>
  );
}
