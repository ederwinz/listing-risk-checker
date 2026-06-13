import { CompareIcon } from "./icons";

export function BrandMark() {
  return (
    <div className="brandmark">
      <span className="glyph">
        <CompareIcon style={{ color: "var(--on-brand)" }} />
      </span>
      <span className="wordmark">Counterpart</span>
    </div>
  );
}
