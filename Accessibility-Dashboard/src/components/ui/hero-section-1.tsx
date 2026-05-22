import React from 'react';
import { Menu, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { AnimatedGroup } from '@/components/ui/animated-group';
import { cn } from '@/lib/utils';

const transitionVariants = {
  item: {
    hidden: {
      opacity: 0,
      filter: 'blur(12px)',
      y: 12
    },
    visible: {
      opacity: 1,
      filter: 'blur(0px)',
      y: 0,
      transition: {
        bounce: 0.3,
        duration: 1.5
      }
    }
  }
};

interface HeroSectionProps {
  onLoginClick?: () => void;
}

export function HeroSection({ onLoginClick }: HeroSectionProps) {
  return (
    <>
      <HeroHeader onLoginClick={onLoginClick} />
      <main className="overflow-hidden bg-[radial-gradient(circle_at_top,_#f8fbff_0%,_#f1f5f9_45%,_#e9eef5_100%)]">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 isolate z-[2] hidden opacity-50 lg:block"
        >
          <div className="absolute left-0 top-0 h-[80rem] w-[35rem] -translate-y-[350px] -rotate-45 rounded-full bg-[radial-gradient(68.54%_68.72%_at_55.02%_31.46%,hsla(214,25%,85%,.24)_0,hsla(214,18%,65%,.08)_50%,hsla(214,16%,45%,0)_80%)]" />
          <div className="absolute left-0 top-0 h-[80rem] w-56 -rotate-45 rounded-full bg-[radial-gradient(50%_50%_at_50%_50%,hsla(214,25%,85%,.20)_0,hsla(214,16%,45%,.05)_80%,transparent_100%)] [translate:5%_-50%]" />
          <div className="absolute left-0 top-0 h-[80rem] w-56 -translate-y-[350px] -rotate-45 bg-[radial-gradient(50%_50%_at_50%_50%,hsla(214,25%,85%,.18)_0,hsla(214,16%,45%,.03)_80%,transparent_100%)]" />
        </div>

        <section>
          <div className="relative pt-24 md:pt-36">
            <AnimatedGroup
              variants={{
                container: {
                  visible: {
                    transition: {
                      delayChildren: 1
                    }
                  }
                },
                item: {
                  hidden: {
                    opacity: 0,
                    y: 20
                  },
                  visible: {
                    opacity: 1,
                    y: 0,
                    transition: {
                      bounce: 0.3,
                      duration: 2
                    }
                  }
                }
              }}
              className="absolute inset-0 -z-20"
            >
              <img
                src="https://images.unsplash.com/photo-1461749280684-dccba630e2f6?auto=format&fit=crop&w=2200&q=80"
                alt="background"
                className="absolute inset-x-0 top-56 -z-20 hidden opacity-40 lg:top-32 lg:block"
                width="2200"
                height="1400"
              />
            </AnimatedGroup>

            <div
              aria-hidden
              className="absolute inset-0 -z-10 size-full [background:radial-gradient(125%_125%_at_50%_100%,transparent_0%,#f1f5f9_75%)]"
            />

            <div className="mx-auto max-w-7xl px-6">
              <div className="text-center sm:mx-auto lg:mr-auto lg:mt-0">
                <AnimatedGroup variants={transitionVariants}>
                  <h1 className="mx-auto mt-8 max-w-4xl text-balance text-5xl font-black tracking-tight text-slate-900 md:text-7xl lg:mt-16 xl:text-[5.25rem]">
                    UNI Access: 웹 접근성 평가를 쉽고 정확하게
                  </h1>
                  <p className="mx-auto mt-8 max-w-2xl text-balance text-lg text-slate-600">
                    고령자와 장애인을 위한 페이지 적합도를 점수화하고, 프로젝트 단위로 통합 관리하는
                    접근성 대시보드
                  </p>
                </AnimatedGroup>

                <AnimatedGroup
                  variants={{
                    container: {
                      visible: {
                        transition: {
                          staggerChildren: 0.05,
                          delayChildren: 0.75
                        }
                      }
                    },
                    ...transitionVariants
                  }}
                  className="mt-12 flex flex-col items-center justify-center gap-2 md:flex-row"
                >
                  <div key={1} className="rounded-[14px] border border-slate-300/70 bg-slate-900/5 p-0.5">
                    <Button
                      size="lg"
                      className="rounded-xl px-5 text-base"
                      onClick={() => onLoginClick?.()}
                    >
                      <span className="text-nowrap">로그인 시작</span>
                    </Button>
                  </div>
                  <Button key={2} size="lg" variant="ghost" className="h-10 rounded-xl px-5">
                    <span className="text-nowrap">데모 요청</span>
                  </Button>
                </AnimatedGroup>
              </div>
            </div>

            <AnimatedGroup
              variants={{
                container: {
                  visible: {
                    transition: {
                      staggerChildren: 0.05,
                      delayChildren: 0.75
                    }
                  }
                },
                ...transitionVariants
              }}
            >
              <div className="relative -mr-56 mt-8 overflow-hidden px-2 sm:mr-0 sm:mt-12 md:mt-20">
                <div aria-hidden className="absolute inset-0 z-10 bg-gradient-to-b from-transparent from-35% to-slate-100" />
                <div className="relative mx-auto max-w-6xl overflow-hidden rounded-2xl border border-slate-200 bg-white p-4 shadow-lg shadow-slate-950/10 ring-1 ring-white/60">
                  <DashboardPreviewMockup />
                </div>
              </div>
            </AnimatedGroup>
          </div>
        </section>

      </main>
    </>
  );
}

const menuItems = [
  { name: 'Features', href: '#' },
  { name: 'Solution', href: '#' },
  { name: 'Pricing', href: '#' },
  { name: 'About', href: '#' }
];

const HeroHeader = ({ onLoginClick }: { onLoginClick?: () => void }) => {
  const [menuState, setMenuState] = React.useState(false);
  const [isScrolled, setIsScrolled] = React.useState(false);

  React.useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 50);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <header>
      <nav data-state={menuState && 'active'} className="group fixed z-20 w-full px-2">
        <div
          className={cn(
            'mx-auto mt-2 max-w-6xl px-6 transition-all duration-300 lg:px-12',
            isScrolled && 'max-w-4xl rounded-2xl bg-white/70 shadow-sm backdrop-blur-lg lg:px-5'
          )}
        >
          <div className="relative flex flex-wrap items-center justify-between gap-6 py-3 lg:gap-0 lg:py-4">
            <div className="flex w-full justify-between lg:w-auto">
              <a href="#" aria-label="home" className="flex items-center space-x-2">
                <Logo />
              </a>

              <button
                onClick={() => setMenuState(!menuState)}
                aria-label={menuState === true ? 'Close Menu' : 'Open Menu'}
                className="relative z-20 -m-2.5 -mr-4 block cursor-pointer p-2.5 lg:hidden"
              >
                <Menu className="m-auto size-6 duration-200 group-data-[state=active]:scale-0 group-data-[state=active]:opacity-0" />
                <X className="absolute inset-0 m-auto size-6 -rotate-180 scale-0 opacity-0 duration-200 group-data-[state=active]:rotate-0 group-data-[state=active]:scale-100 group-data-[state=active]:opacity-100" />
              </button>
            </div>

            <div className="absolute inset-0 m-auto hidden size-fit lg:block">
              <ul className="flex gap-8 text-sm">
                {menuItems.map((item) => (
                  <li key={item.name}>
                    <a href={item.href} className="block text-slate-600 duration-150 hover:text-slate-900">
                      <span>{item.name}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>

            <div className="mb-6 hidden w-full flex-wrap items-center justify-end space-y-8 rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl shadow-zinc-300/20 group-data-[state=active]:block md:flex-nowrap lg:m-0 lg:flex lg:w-fit lg:gap-6 lg:space-y-0 lg:border-transparent lg:bg-transparent lg:p-0 lg:shadow-none">
              <div className="lg:hidden">
                <ul className="space-y-6 text-base">
                  {menuItems.map((item) => (
                    <li key={item.name}>
                      <a href={item.href} className="block text-slate-600 duration-150 hover:text-slate-900">
                        <span>{item.name}</span>
                      </a>
                    </li>
                  ))}
                </ul>
              </div>

              <div className="flex w-full flex-col space-y-3 sm:flex-row sm:gap-3 sm:space-y-0 md:w-fit">
                <Button variant="outline" size="sm" className={cn(isScrolled && 'lg:hidden')} onClick={() => onLoginClick?.()}>
                  <span>Login</span>
                </Button>
                <Button size="sm" className={cn(isScrolled && 'lg:hidden')}>
                  <span>Sign Up</span>
                </Button>
                <Button size="sm" className={cn(isScrolled ? 'lg:inline-flex' : 'hidden')} onClick={() => onLoginClick?.()}>
                  <span>Get Started</span>
                </Button>
              </div>
            </div>
          </div>
        </div>
      </nav>
    </header>
  );
};

const Logo = ({ className }: { className?: string }) => {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div className="h-5 w-5 rounded-sm bg-gradient-to-br from-indigo-400 to-emerald-400" />
      <span className="text-sm font-black tracking-[0.18em] text-slate-800">UNI Access</span>
    </div>
  );
};

const DashboardPreviewMockup = () => {
  return (
    <div className="relative aspect-[15/8] overflow-hidden rounded-2xl border border-slate-200 bg-[#12151b]">
      <div className="absolute inset-y-0 left-0 w-[12.5%] border-r border-white/5 bg-[#0b0e13]" />
      <div className="absolute left-[2.2%] top-[4.5%] h-[3.5%] w-[1.6%] rounded-full bg-indigo-300/80" />

      <div className="absolute left-[2%] top-[14%] flex flex-col gap-[6.5%]">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="h-[1.6rem] w-[1.6rem] rounded-lg border border-white/6 bg-white/[0.02]" />
        ))}
      </div>

      <div className="absolute inset-y-0 left-[12.5%] right-0 bg-[#13161d]" />

      <div className="absolute left-[15.5%] top-[5%]">
        <p className="text-[0.55rem] font-black tracking-[0.28em] text-slate-400">UNI ACCESS</p>
        <h3 className="mt-2 text-[1.8rem] font-black tracking-tight text-white">대시보드</h3>
      </div>

      <div className="absolute right-[2.5%] top-[4.2%] flex items-center gap-2 rounded-[1.2rem] border border-white/6 bg-white/[0.04] px-3 py-2 shadow-[0_12px_30px_rgba(0,0,0,0.28)]">
        <div className="h-8 w-8 rounded-full border border-white/8 bg-white/[0.05]" />
        <div className="h-8 w-8 rounded-full border border-white/8 bg-white/[0.05]" />
        <div className="h-8 w-8 rounded-full border border-white/8 bg-white/[0.05]" />
      </div>

      <div className="absolute left-[15.5%] right-[2.5%] top-[15.5%] grid grid-cols-[1.15fr_0.85fr_0.85fr] gap-4">
        <section className="rounded-2xl bg-[#0d1015] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]">
          <div className="flex items-start justify-between">
            <div>
              <p className="text-sm font-bold text-white">월별 접근성 점수 추이</p>
              <p className="mt-3 text-[0.55rem] font-bold tracking-[0.12em] text-cyan-200/70">현재 점수</p>
              <div className="mt-2 flex items-end gap-1">
                <span className="text-[3.2rem] font-black leading-none tracking-[-0.05em] text-white">87</span>
                <span className="pb-1 text-xl font-bold text-cyan-100/85">점</span>
              </div>
            </div>
            <div className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-1 text-[0.58rem] font-semibold text-slate-300">
              최근 6개월
            </div>
          </div>
          <div className="mt-4 h-[11.8rem] overflow-hidden rounded-b-2xl">
            <svg viewBox="0 0 620 176" preserveAspectRatio="none" className="h-full w-full">
              <defs>
                <linearGradient id="hero-dashboard-area" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="rgba(255,255,255,0.12)" />
                  <stop offset="100%" stopColor="rgba(255,255,255,0.02)" />
                </linearGradient>
              </defs>
              <path
                d="M0 124 C70 98 128 82 190 88 C250 94 282 126 336 114 C386 102 432 64 506 70 C548 74 582 72 620 68 L620 176 L0 176 Z"
                fill="url(#hero-dashboard-area)"
              />
              <path
                d="M0 124 C70 98 128 82 190 88 C250 94 282 126 336 114 C386 102 432 64 506 70 C548 74 582 72 620 68"
                fill="none"
                stroke="rgba(255,255,255,0.95)"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </div>
        </section>

        <section className="rounded-2xl bg-[#0d1015] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]">
          <p className="text-sm font-bold text-white">접근성 분야별 평균 점수</p>
          <p className="mt-1 text-xs text-slate-400">분야별 평균 점수를 비교합니다.</p>
          <div className="mt-4 flex items-center justify-center">
            <svg viewBox="0 0 220 220" className="h-[13rem] w-[13rem]">
              <polygon points="110,32 180,110 110,188 40,110" fill="none" stroke="rgba(255,255,255,0.16)" strokeWidth="1" />
              <polygon points="110,52 160,110 110,168 60,110" fill="none" stroke="rgba(255,255,255,0.10)" strokeWidth="1" />
              <polygon points="110,71 143,110 110,149 77,110" fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="1" />
              <polygon points="110,90 126,110 110,130 94,110" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
              <line x1="110" y1="24" x2="110" y2="196" stroke="rgba(255,255,255,0.08)" />
              <line x1="24" y1="110" x2="196" y2="110" stroke="rgba(255,255,255,0.08)" />
              <polygon points="110,47 156,110 110,156 66,110" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.92)" strokeWidth="2" />
              <text x="110" y="16" textAnchor="middle" className="fill-slate-300 text-[10px] font-semibold">인식 가능</text>
              <text x="196" y="114" textAnchor="end" className="fill-slate-300 text-[10px] font-semibold">운용 가능</text>
              <text x="110" y="208" textAnchor="middle" className="fill-slate-300 text-[10px] font-semibold">이해 가능</text>
              <text x="24" y="114" textAnchor="start" className="fill-slate-300 text-[10px] font-semibold">견고성</text>
            </svg>
          </div>
        </section>

        <section className="rounded-2xl bg-[#0d1015] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]">
          <p className="text-sm font-bold text-white">이슈 분야별 비율</p>
          <p className="mt-1 text-xs text-slate-400">분야별 이슈 비중을 확인합니다.</p>
          <div className="mt-5 flex items-center gap-4">
            <div className="flex items-center justify-center">
              <svg viewBox="0 0 220 220" className="h-[12rem] w-[12rem] -rotate-90">
                <circle cx="110" cy="110" r="66" fill="none" stroke="rgba(148,163,184,0.08)" strokeWidth="20" />
                <circle cx="110" cy="110" r="66" fill="none" stroke="#818cf8" strokeWidth="20" strokeDasharray="219 196" strokeDashoffset="0" />
                <circle cx="110" cy="110" r="66" fill="none" stroke="#22c55e" strokeWidth="20" strokeDasharray="126 289" strokeDashoffset="-219" />
                <circle cx="110" cy="110" r="66" fill="none" stroke="#f59e0b" strokeWidth="20" strokeDasharray="70 345" strokeDashoffset="-345" />
              </svg>
            </div>
            <div className="space-y-4">
              {[
                { label: '인식 가능', value: '53%', color: '#818cf8' },
                { label: '이해 가능', value: '31%', color: '#22c55e' },
                { label: '운용 가능', value: '16%', color: '#f59e0b' }
              ].map((item) => (
                <div key={item.label} className="flex items-center gap-3 text-sm">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                  <span className="font-semibold text-slate-200">{item.label}</span>
                  <span className="text-slate-400">{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      <div className="absolute left-[15.5%] right-[2.5%] top-[57%] grid grid-cols-[0.95fr_1.85fr] gap-4">
        <section className="rounded-2xl bg-[#0d1015] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]">
          <p className="text-sm font-bold text-white">가장 취약한 분야 Top 5</p>
          <p className="mt-1 text-xs text-slate-400">프로젝트별 우선 개선 항목</p>
          <div className="mt-4 space-y-2.5">
            {[
              ['고령자 접근성 포털', '이해 가능', '77점'],
              ['고령자 접근성 포털', '인식 가능', '78점'],
              ['고령자 접근성 포털', '운용 가능', '78점'],
              ['고령자 접근성 포털', '견고성', '80점'],
              ['의료기관 가이드 점검', '이해 가능', '84점']
            ].map(([name, area, score], index) => (
              <div key={`${name}-${area}`} className="flex items-center justify-between rounded-xl border border-white/8 bg-white/[0.02] px-3 py-2.5">
                <div className="flex items-center gap-3">
                  <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-white/[0.06] text-xs font-bold text-slate-200">
                    {index + 1}
                  </span>
                  <div>
                    <p className="text-sm font-semibold text-white">{name}</p>
                    <p className="text-xs text-slate-400">{area}</p>
                  </div>
                </div>
                <span className="text-xl font-black text-white">{score}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl bg-[#0d1015] p-4 shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)]">
          <p className="text-sm font-bold text-white">최근 스캔 작업</p>
          <p className="mt-1 text-xs text-slate-400">대상 사이트별 스캔 결과</p>
          <div className="mt-4 overflow-hidden rounded-xl border border-white/8">
            <div className="grid grid-cols-[1.15fr_1fr_0.7fr_0.5fr_1fr] bg-white/[0.03] px-4 py-3 text-[0.62rem] font-semibold tracking-[0.08em] text-slate-500 uppercase">
              <span>프로젝트</span>
              <span>대상 사이트</span>
              <span>상태</span>
              <span>점수</span>
              <span>완료 시각</span>
            </div>
            {[
              ['홍익대학교 홈페이지 접근성 평가', '홍익대학교 도서관', '완료', '92점', '2026-03-13'],
              ['홍익대학교 홈페이지 접근성 평가', '홍익대학교 입학안내', '완료', '84점', '2026-03-12'],
              ['홍익대학교 홈페이지 접근성 평가', '홍익대학교 메인 홈페이지', '완료', '89점', '2026-03-11'],
              ['고령자 접근성 포털', '시청 메인 포털', '완료', '83점', '2026-03-05'],
              ['의료기관 가이드 점검', '병원 홈페이지', '진행중', '-', '-']
            ].map(([project, site, status, score, date], index) => (
              <div
                key={`${project}-${site}-${index}`}
                className="grid grid-cols-[1.15fr_1fr_0.7fr_0.5fr_1fr] items-center border-t border-white/6 px-4 py-3 text-xs"
              >
                <span className="truncate font-semibold text-white">{project}</span>
                <span className="truncate text-slate-300">{site}</span>
                <span>
                  <span className={cn(
                    'inline-flex rounded-md px-2.5 py-1 text-[10px] font-bold',
                    status === '진행중'
                      ? 'bg-sky-500/15 text-sky-300'
                      : 'bg-emerald-500/12 text-emerald-300'
                  )}>
                    {status}
                  </span>
                </span>
                <span className="font-semibold text-white">{score}</span>
                <span className="text-slate-400">{date}</span>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};
