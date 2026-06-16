import Link from "next/link";

const navItems = [
  { href: "/", label: "Home", icon: "⌂" },
  { href: "/search?q=music", label: "Music", icon: "♪" },
  { href: "/search?q=technology", label: "Tech", icon: "⚙" },
];

export function Sidebar() {
  return (
    <aside className="fixed bottom-0 left-0 top-14 z-30 hidden w-[200px] border-r border-zinc-200 bg-white px-3 py-4 md:block">
      <nav className="flex flex-col gap-1" aria-label="Primary">
        {navItems.map((item) => (
          <Link key={item.href} href={item.href} className="flex items-center gap-4 rounded-xl px-3 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-100">
            <span className="w-5 text-center text-lg">{item.icon}</span>
            {item.label}
          </Link>
        ))}
      </nav>
    </aside>
  );
}
