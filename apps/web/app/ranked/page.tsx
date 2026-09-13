import Link from 'next/link';

const divisions = ['Новичок', 'Бронза', 'Серебро', 'Золото', 'Платина', 'Алмаз', 'Мастер', 'Грандмастер'];

export default function RankedPage() {
  return (
    <main className="shell subPage">
      <Link className="brand" href="/">БУКВОГОН</Link>
      <div className="eyebrow">СОРЕВНОВАТЕЛЬНЫЙ РЕЖИМ</div>
      <h1>Ranked <span>Season 0</span></h1>
      <p className="lead narrow">Одинаковый текст, строгие правила е/ё, server-authoritative результат и рейтинг без платных преимуществ.</p>

      <div className="rankPanel">
        <div>
          <span className="label">ДОСТУП</span>
          <strong>БуквоГон Pro</strong>
          <p>300 ₽/месяц. Подписка открывает соревновательную инфраструктуру, а не силу.</p>
        </div>
        <Link className="pill primary" href="/pro">Открыть Ranked</Link>
      </div>

      <section className="section compact">
        <div className="eyebrow">ДИВИЗИОНЫ</div>
        <div className="divisionRow">
          {divisions.map((division, index) => <span key={division}>{index + 1}. {division}</span>)}
        </div>
      </section>
    </main>
  );
}
