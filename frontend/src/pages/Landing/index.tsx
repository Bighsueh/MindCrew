import { Link } from 'react-router-dom'
import { ArrowRight, Lightbulb, Users, Zap, MessageSquare, LayoutGrid, BarChart3 } from 'lucide-react'
import { StickyNoteSVG } from '@/components/landing/StickyNoteSVG'
import heroBgVideo from '@/assets/hero-bg.mp4'

export function LandingPage() {
  return (
    <div className="overflow-x-hidden">
      {/* ─── Navbar ─── */}
      <nav className="fixed top-0 left-0 right-0 z-50 backdrop-blur-md bg-bg/80 border-b border-border-light">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          <span className="text-xl font-bold tracking-tight text-primary">MindCrew</span>
          <div className="hidden items-center gap-8 md:flex">
            <a href="#features" className="text-sm text-text-muted transition-colors hover:text-text">功能</a>
            <a href="#process" className="text-sm text-text-muted transition-colors hover:text-text">流程</a>
            <a href="#faq" className="text-sm text-text-muted transition-colors hover:text-text">常見問題</a>
          </div>
          <div className="flex items-center gap-3">
            <Link
              to="/login"
              className="text-sm font-medium text-text-muted transition-colors hover:text-text"
            >
              登入
            </Link>
            <Link
              to="/register"
              className="rounded-full bg-primary px-5 py-2 text-sm font-semibold text-text-inverse transition-colors hover:bg-primary-light cursor-pointer"
            >
              免費開始
            </Link>
          </div>
        </div>
      </nav>

      {/* ─── Hero ─── */}
      <section className="relative flex min-h-svh flex-col items-center justify-center px-6 pt-16">
        {/* Full-bleed video background */}
        <div className="absolute inset-0 overflow-hidden">
          <video
            autoPlay
            loop
            muted
            playsInline
            className="h-full w-full object-cover"
          >
            <source src={heroBgVideo} type="video/mp4" />
          </video>
          <div className="absolute inset-0 bg-bg/60" />
        </div>

        <div className="relative z-10 mx-auto max-w-5xl text-center">
          <h1 className="animate-fade-up text-[clamp(3.5rem,10vw,9rem)] font-extrabold leading-[0.9] tracking-[-0.04em] text-primary">
            MIND
            <br />
            CREW
          </h1>
          <p className="animate-fade-up mx-auto mt-8 max-w-xl text-lg leading-relaxed text-text-muted" style={{ animationDelay: '0.15s' }}>
            AI 驅動的 Design Thinking 協作平台。
            <br />
            五位 AI 隊友，與你一起發散、收斂、創造。
          </p>
          <div className="animate-fade-up mt-10 flex flex-wrap items-center justify-center gap-4" style={{ animationDelay: '0.3s' }}>
            <Link
              to="/register"
              className="group flex items-center gap-2 rounded-full bg-primary px-8 py-3.5 text-sm font-semibold text-text-inverse transition-all hover:bg-primary-light hover:shadow-lg cursor-pointer"
            >
              開始協作
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-1" />
            </Link>
            <a
              href="#process"
              className="rounded-full border border-border px-8 py-3.5 text-sm font-medium text-text transition-colors hover:bg-surface cursor-pointer"
            >
              了解更多
            </a>
          </div>
        </div>

        {/* Floating sticky notes decoration */}
        <div className="animate-fade-up pointer-events-none absolute bottom-8 left-0 right-0 z-10 flex justify-center gap-6 opacity-80" style={{ animationDelay: '0.5s' }}>
          <StickyNoteSVG color="#F5E6C8" rotation={-6} text="痛點" />
          <StickyNoteSVG color="#F0D9C4" rotation={3} text="洞察" />
          <StickyNoteSVG color="#D4E4C8" rotation={-2} text="點子" />
          <StickyNoteSVG color="#C8D8E8" rotation={5} text="方案" />
        </div>
      </section>

      {/* ─── Statement (dark) ─── */}
      <section className="bg-bg-dark px-6 py-28">
        <div className="mx-auto max-w-4xl">
          <div className="grid gap-12 md:grid-cols-2 md:items-center">
            <div>
              <p className="text-sm font-medium uppercase tracking-widest text-text-muted-on-dark">/01</p>
              <h2 className="mt-4 text-3xl font-bold leading-tight text-text-on-dark md:text-4xl">
                更乾淨的
                <br />
                創意環境
              </h2>
            </div>
            <div>
              <p className="text-base leading-relaxed text-text-muted-on-dark">
                MindCrew 讓你的 Design Thinking 工作坊不再受限於人數和時間。
                AI 隊友隨時待命，在你需要發散的時候帶來多元觀點，在收斂的時候協助歸納整理。
              </p>
              <p className="mt-4 text-base leading-relaxed text-text-muted-on-dark">
                無論是課堂教學、團隊腦力激盪，或是獨立研究——打開專案，AI 團隊已就位。
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Visual showcase (light, with sticky note illustration) ─── */}
      <section className="px-6 py-28">
        <div className="mx-auto max-w-6xl">
          <div className="grid gap-8 md:grid-cols-5">
            {/* Left: large visual area */}
            <div className="md:col-span-3">
              <div className="relative aspect-[4/3] overflow-hidden rounded-2xl bg-bg-warm">
                <div className="absolute inset-0 flex items-center justify-center p-8">
                  <div className="grid grid-cols-3 gap-4">
                    {[
                      { color: '#F5E6C8', text: '使用者在哪裡遇到困難？', rot: -2 },
                      { color: '#F0D9C4', text: '痛點：等待時間太長', rot: 1 },
                      { color: '#D4E4C8', text: '如果能自動分類呢？', rot: -1 },
                      { color: '#C8D8E8', text: 'HMW: 如何減少步驟？', rot: 3 },
                      { color: '#EEDCE4', text: '整合 AI 輔助建議', rot: -3 },
                      { color: '#F5E6C8', text: '原型：一鍵匯出摘要', rot: 2 },
                    ].map((note, i) => (
                      <div
                        key={i}
                        className="flex aspect-square items-center justify-center rounded-md p-4 shadow-md transition-transform duration-500 hover:scale-105"
                        style={{
                          backgroundColor: note.color,
                          transform: `rotate(${note.rot}deg)`,
                        }}
                      >
                        <p className="text-center text-xs font-medium text-primary/80 leading-snug">
                          {note.text}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="absolute bottom-4 right-6 flex items-center gap-2 rounded-full bg-surface/90 px-4 py-2 shadow-sm">
                  <div className="h-1 w-8 rounded-full bg-primary/60" />
                  <span className="text-[10px] font-medium text-text-muted">AI Crew 2 正在寫…</span>
                </div>
              </div>
            </div>

            {/* Right: feature text */}
            <div className="flex flex-col justify-center md:col-span-2">
              <p className="text-sm font-medium uppercase tracking-widest text-text-muted">/02</p>
              <h2 className="mt-4 text-3xl font-bold leading-tight text-primary md:text-4xl">
                即時協作白板
              </h2>
              <p className="mt-4 text-base leading-relaxed text-text-muted">
                基於 tldraw 打造的共享白板，便條紙即時同步、AI 與人類操作外觀完全一致。
                CRDT 技術確保延遲低於 200ms。
              </p>
              <ul className="mt-6 space-y-3">
                {['便條紙新增 / 編輯 / 分群', '人類與 AI 操作無差異', '所見即所得，即時同步'].map((item) => (
                  <li key={item} className="flex items-center gap-2 text-sm text-text">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[10px] text-text-inverse">✓</span>
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Process — Double Diamond (dark) ─── */}
      <section id="process" className="bg-bg-dark px-6 py-28">
        <div className="mx-auto max-w-5xl text-center">
          <p className="text-sm font-medium uppercase tracking-widest text-text-muted-on-dark">/03</p>
          <h2 className="mt-4 text-3xl font-bold text-text-on-dark md:text-5xl">
            雙鑽石設計流程
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-base text-text-muted-on-dark">
            四個階段，從發散到收斂，AI 自動適應每個階段的行為策略
          </p>

          <div className="mt-16 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { phase: 'Discover', desc: '發散：探索痛點與需求', icon: Lightbulb, tag: '發散' },
              { phase: 'Define', desc: '收斂：歸納洞察與 HMW', icon: LayoutGrid, tag: '收斂' },
              { phase: 'Develop', desc: '發散：快速發想解決方案', icon: Zap, tag: '發散' },
              { phase: 'Deliver', desc: '收斂：評估可行性與排序', icon: BarChart3, tag: '收斂' },
            ].map((item, i) => (
              <div
                key={item.phase}
                className="group rounded-xl border border-border-dark bg-surface-dark p-6 text-left transition-all hover:border-accent/40 hover:bg-surface-dark/80"
              >
                <div className="flex items-center justify-between">
                  <item.icon size={24} className="text-text-muted-on-dark group-hover:text-text-on-dark transition-colors" />
                  <span className="rounded-full border border-border-dark px-2.5 py-0.5 text-[10px] font-medium text-text-muted-on-dark">
                    {item.tag}
                  </span>
                </div>
                <h3 className="mt-4 text-xl font-bold text-text-on-dark">{item.phase}</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-muted-on-dark">{item.desc}</p>
                <div className="mt-4 text-xs text-accent-light">0{i + 1}/04</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Features grid (light) ─── */}
      <section id="features" className="px-6 py-28">
        <div className="mx-auto max-w-5xl">
          <p className="text-sm font-medium uppercase tracking-widest text-text-muted">/04</p>
          <h2 className="mt-4 text-3xl font-bold text-primary md:text-5xl">
            為什麼選擇 MindCrew
          </h2>

          <div className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
            {[
              {
                icon: Users,
                title: '1 Supervisor + 4 Crew',
                desc: 'AI 團隊各司其職：Supervisor 引導方向，Crew 積極貢獻觀點。人類可隨時替換任一席位。',
              },
              {
                icon: MessageSquare,
                title: '即時聊天室',
                desc: 'AI 先說再做——每次白板操作前先在聊天室說明意圖，像真正的團隊成員一樣溝通。',
              },
              {
                icon: Zap,
                title: '全 AI 自主模式',
                desc: '建立專案後讓 AI 自行運作，事後回來看成果。人類可隨時加入或離開。',
              },
              {
                icon: LayoutGrid,
                title: '教師儀表板',
                desc: '一覽所有專案的即時狀態、觀察模式不佔席位、課後紀錄完整回顧。',
              },
              {
                icon: Lightbulb,
                title: 'AI 決策透明',
                desc: '教師可回溯每一次 AI 決策的思考歷程：觀察了什麼、為何介入、執行了什麼。',
              },
              {
                icon: BarChart3,
                title: 'LLM 用量追蹤',
                desc: '追蹤每個專案的 AI 運算資源消耗，精確到各 Agent 的 input/output token 分布。',
              },
            ].map((feature) => (
              <div
                key={feature.title}
                className="group rounded-xl border border-border bg-surface p-6 transition-all hover:shadow-lg"
              >
                <feature.icon
                  size={28}
                  strokeWidth={1.5}
                  className="text-text-muted group-hover:text-primary transition-colors"
                />
                <h3 className="mt-4 text-base font-bold text-text">{feature.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-text-muted">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── FAQ (warm bg) ─── */}
      <section id="faq" className="bg-bg-warm px-6 py-28">
        <div className="mx-auto max-w-3xl">
          <p className="text-sm font-medium uppercase tracking-widest text-text-muted">/05</p>
          <h2 className="mt-4 text-3xl font-bold text-primary md:text-4xl">
            常見問題
          </h2>

          <div className="mt-12 space-y-4">
            {[
              {
                q: '學生可以自行註冊嗎？',
                a: '不行。學生帳號由教師統一建立與管理，確保教學場景下的帳號管控。',
              },
              {
                q: 'AI 會不會太主動，壓過學生的發言？',
                a: 'AI 內建節奏控制——偵測到人類正在輸入時會暫停，連續發言不超過 3 則。教師還可以透過「AI 貢獻度」調整 AI 的活躍程度。',
              },
              {
                q: '支援手機嗎？',
                a: '目前支援桌面（≥1024px）與平板（768px 以上）。白板協作需要足夠的螢幕空間，暫不支援手機。',
              },
              {
                q: '可以只讓 AI 跑完整個流程嗎？',
                a: '可以。建立專案後不加入任何席位，5 個 AI Agent 會自主完成四階段流程。你可以隨時加入，也可以事後查看完整紀錄。',
              },
            ].map((item) => (
              <details
                key={item.q}
                className="group rounded-lg border border-border bg-surface"
              >
                <summary className="flex cursor-pointer items-center justify-between px-6 py-5 text-sm font-semibold text-text transition-colors hover:text-primary">
                  {item.q}
                  <span className="ml-4 shrink-0 text-text-muted transition-transform group-open:rotate-45">+</span>
                </summary>
                <div className="px-6 pb-5 text-sm leading-relaxed text-text-muted">
                  {item.a}
                </div>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA footer (dark) ─── */}
      <section className="bg-bg-dark px-6 py-28">
        <div className="mx-auto max-w-4xl text-center">
          <h2 className="text-[clamp(2.5rem,6vw,5rem)] font-extrabold leading-[0.95] tracking-[-0.03em] text-text-on-dark">
            MIND
            <br />
            CREW
          </h2>
          <p className="mx-auto mt-6 max-w-md text-base text-text-muted-on-dark">
            讓 AI 成為你的 Design Thinking 最佳隊友
          </p>
          <Link
            to="/register"
            className="mt-10 inline-flex items-center gap-2 rounded-full border border-text-on-dark/20 bg-transparent px-10 py-4 text-sm font-semibold text-text-on-dark transition-all hover:bg-text-on-dark hover:text-bg-dark cursor-pointer"
          >
            免費開始
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* ─── Footer ─── */}
      <footer className="border-t border-border px-6 py-8">
        <div className="mx-auto flex max-w-7xl items-center justify-between">
          <span className="text-sm text-text-muted">© 2026 MindCrew</span>
          <div className="flex gap-6">
            <a href="#" className="text-xs text-text-muted hover:text-text">隱私政策</a>
            <a href="#" className="text-xs text-text-muted hover:text-text">服務條款</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
