import type { RaceVisualThemeId } from '../../lib/race-visuals';

type RaceVisualProps = Readonly<{
  theme: RaceVisualThemeId;
  variant: number;
  label: string;
}>;

function CarVisual() {
  return (
    <div className="visualCar">
      <span className="visualCar__roof" />
      <span className="visualCar__window" />
      <span className="visualCar__wheel visualCar__wheel--front" />
      <span className="visualCar__wheel visualCar__wheel--rear" />
    </div>
  );
}

function CatVisual() {
  return (
    <div className="visualCat">
      <span className="visualCat__tail" />
      <span className="visualCat__body" />
      <span className="visualCat__head">
        <i className="visualCat__ear visualCat__ear--left" />
        <i className="visualCat__ear visualCat__ear--right" />
        <i className="visualCat__eye visualCat__eye--left" />
        <i className="visualCat__eye visualCat__eye--right" />
      </span>
      <span className="visualCat__paw visualCat__paw--front" />
      <span className="visualCat__paw visualCat__paw--rear" />
    </div>
  );
}

function CaterpillarVisual() {
  return (
    <div className="visualCaterpillar">
      <span className="visualCaterpillar__segment" />
      <span className="visualCaterpillar__segment" />
      <span className="visualCaterpillar__segment" />
      <span className="visualCaterpillar__segment" />
      <span className="visualCaterpillar__head">
        <i className="visualCaterpillar__antenna visualCaterpillar__antenna--left" />
        <i className="visualCaterpillar__antenna visualCaterpillar__antenna--right" />
        <i className="visualCaterpillar__eye" />
      </span>
    </div>
  );
}

function PlaneVisual() {
  return (
    <div className="visualPlane">
      <span className="visualPlane__body" />
      <span className="visualPlane__cockpit" />
      <span className="visualPlane__wing visualPlane__wing--top" />
      <span className="visualPlane__wing visualPlane__wing--bottom" />
      <span className="visualPlane__tail" />
    </div>
  );
}

export function RaceVisual({ theme, variant, label }: RaceVisualProps) {
  const safeVariant = ((Math.trunc(variant) % 4) + 4) % 4;

  return (
    <div
      className={`raceVisual raceVisual--${theme} raceVisual--v${safeVariant}`}
      data-theme={theme}
      data-variant={safeVariant}
      role="img"
      aria-label={label}
    >
      {theme === 'cars' && <CarVisual />}
      {theme === 'cats' && <CatVisual />}
      {theme === 'caterpillars' && <CaterpillarVisual />}
      {theme === 'planes' && <PlaneVisual />}
    </div>
  );
}
