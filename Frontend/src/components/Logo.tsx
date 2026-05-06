interface Props {
  size?: number;
}

export default function Logo({ size = 48 }: Props) {
  return (
    <svg width={size} height={size} viewBox="0 0 48 48" aria-hidden>
      <circle cx="24" cy="24" r="24" fill="#161f1d" />
      <path
        d="M24 11 C28 16 30 22 30 29 C30 35.5 27.5 41 24 44 C20.5 41 18 35.5 18 29 C18 22 20 16 24 11 Z"
        fill="#E8C556"
      />
      <path
        d="M1 27 C6 19 12 33 20 25 C26 19 30 31 38 24 C41 21 44 22 47 20"
        fill="none"
        stroke="#56E8C7"
        strokeWidth="3.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="24" cy="24" r="22.5" fill="none" stroke="#56E8C7" strokeWidth="1" opacity="0.25" />
    </svg>
  );
}
