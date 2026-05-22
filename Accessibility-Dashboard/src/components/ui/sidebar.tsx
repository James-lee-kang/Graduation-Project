import { cn } from "@/lib/utils";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import React, { createContext, useContext, useEffect, useState } from "react";

export interface SidebarItem {
  label: string;
  href?: string;
  icon: React.ReactNode;
  onClick?: () => void;
  active?: boolean;
}

interface SidebarContextProps {
  open: boolean;
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  animate: boolean;
}

const SidebarContext = createContext<SidebarContextProps | undefined>(undefined);

export function useSidebar() {
  const context = useContext(SidebarContext);
  if (!context) {
    throw new Error("useSidebar must be used within a SidebarProvider");
  }
  return context;
}

export function SidebarProvider({
  children,
  open: openProp,
  setOpen: setOpenProp,
  animate = true
}: {
  children: React.ReactNode;
  open?: boolean;
  setOpen?: React.Dispatch<React.SetStateAction<boolean>>;
  animate?: boolean;
}) {
  const [openState, setOpenState] = useState(false);

  const open = openProp !== undefined ? openProp : openState;
  const setOpen = setOpenProp !== undefined ? setOpenProp : setOpenState;

  useEffect(() => {
    if (!open) {
      return;
    }

    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [open, setOpen]);

  return <SidebarContext.Provider value={{ open, setOpen, animate }}>{children}</SidebarContext.Provider>;
}

export function Sidebar({
  children,
  open,
  setOpen,
  animate
}: {
  children: React.ReactNode;
  open?: boolean;
  setOpen?: React.Dispatch<React.SetStateAction<boolean>>;
  animate?: boolean;
}) {
  return (
    <SidebarProvider open={open} setOpen={setOpen} animate={animate}>
      {children}
    </SidebarProvider>
  );
}

export function SidebarBody(props: React.ComponentProps<typeof motion.div>) {
  return (
    <>
      <DesktopSidebar {...props} />
      <MobileSidebar {...(props as React.ComponentProps<"div">)} />
    </>
  );
}

export function DesktopSidebar({
  className,
  children,
  ...props
}: React.ComponentProps<typeof motion.div>) {
  const { open, setOpen, animate } = useSidebar();

  return (
    <>
      <AnimatePresence>
        {open && (
          <motion.button
            type="button"
            aria-label="사이드바 닫기"
            className="fixed inset-0 z-40 hidden cursor-default bg-black/10 md:block"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            onClick={() => setOpen(false)}
          />
        )}
      </AnimatePresence>
      <AnimatePresence>
        {open && (
          <motion.aside
            className={cn(
              "dashboard-drawer fixed top-4 bottom-4 left-4 z-50 hidden w-[290px] overflow-hidden rounded-[30px] bg-slate-50 p-4 shadow-[0_26px_70px_rgba(15,23,42,0.18)] md:flex md:flex-col",
              className
            )}
            initial={{ x: animate ? -330 : 0, opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: animate ? -330 : 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
            style={{ backfaceVisibility: "hidden", contain: "layout paint style", willChange: "transform, opacity" }}
            {...props}
          >
            {children}
          </motion.aside>
        )}
      </AnimatePresence>
    </>
  );
}

export function MobileSidebar({
  className,
  children
}: React.ComponentProps<"div">) {
  const { open, setOpen } = useSidebar();

  return (
    <>
      <AnimatePresence>
        {open && (
          <>
            <motion.button
              type="button"
              aria-label="사이드바 닫기"
              className="fixed inset-0 z-[90] cursor-default bg-black/10 md:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.18, ease: "easeOut" }}
              onClick={() => setOpen(false)}
            />
            <motion.div
              initial={{ x: "-100%", opacity: 0 }}
              animate={{ x: 0, opacity: 1 }}
              exit={{ x: "-100%", opacity: 0 }}
              transition={{ duration: 0.25, ease: "easeInOut" }}
              className={cn(
                "dashboard-drawer fixed top-3 bottom-3 left-3 z-[100] flex w-[calc(100vw-24px)] max-w-[320px] flex-col rounded-[30px] bg-white p-4 shadow-[0_26px_70px_rgba(15,23,42,0.18)] md:hidden",
                className
              )}
            >
              <button
                type="button"
                className="mb-3 ml-auto inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700"
                aria-label="메뉴 닫기"
                onClick={() => setOpen(false)}
              >
                <X size={18} />
              </button>
              <div className="min-h-0 flex-1">{children}</div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </>
  );
}

export function SidebarLink({
  link,
  className,
  ...props
}: {
  link: SidebarItem;
  className?: string;
} & Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "onClick">) {
  const { open, setOpen, animate } = useSidebar();

  const textNode = (
    <motion.span
      animate={{
        opacity: animate ? (open ? 1 : 0) : 1,
        x: animate ? (open ? 0 : -8) : 0,
        maxWidth: animate ? (open ? 160 : 0) : 160
      }}
      transition={{ duration: 0.15, ease: "easeOut" }}
      className="overflow-hidden whitespace-nowrap text-sm font-medium text-current transition-colors"
    >
      {link.label}
    </motion.span>
  );

  const baseClass = cn(
    "sidebar-nav-link group flex h-10 w-full items-center gap-2 rounded-xl border px-2.5 text-left transition",
    link.active
      ? "sidebar-nav-link-active border-transparent bg-transparent text-slate-900"
      : "border-transparent bg-transparent text-[var(--dashboard-sidebar-muted-text)] hover:border-slate-200 hover:bg-slate-100 hover:text-[var(--dashboard-sidebar-hover-text)]",
    className
  );

  if (link.onClick) {
    return (
      <button
        type="button"
        className={baseClass}
        onClick={() => {
          link.onClick?.();
          setOpen(false);
        }}
        {...props}
      >
        <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center text-current">{link.icon}</span>
        {textNode}
      </button>
    );
  }

  return (
    <a href={link.href ?? "#"} className={baseClass} onClick={() => setOpen(false)}>
      <span className="inline-flex h-5 w-5 shrink-0 items-center justify-center text-current">{link.icon}</span>
      {textNode}
    </a>
  );
}
