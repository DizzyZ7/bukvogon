import Link from 'next/link';

export default function ProPage() {
  return (
    <main className="shell subPage">
      <Link className="brand" href="/">БУКВОГОН</Link>
      <div className="eyebrow">БУКВОГОН PRO</div>
      <h1>Твоя лига.<br /><span>300 ₽ в месяц.</span></h1>
      <p className="lead narrow">Платишь за Ranked, сезоны, лидерборд и глубокую аналитику. Ни одна покупка не увеличивает реальную скорость машины.</p>

      <article className="checkoutCard">
        <div>
          <span className="label">ЕЖЕМЕСЯЧНО</span>
          <div className="bigPrice">300 ₽</div>
          <p>Отмена подписки — без потери обычного аккаунта, гаража и Free-режима.</p>
        </div>
        <button className="pill primary" type="button" disabled>Оплата подключается</button>
      </article>

      <p className="muted">Платежный провайдер будет подключен отдельным адаптером; доменная логика Pro уже не зависит от конкретной кассы.</p>
    </main>
  );
}
