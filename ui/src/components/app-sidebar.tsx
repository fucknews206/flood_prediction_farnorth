import * as React from "react"
import { useLocation, Link } from "react-router-dom"
import {
  LayoutDashboard,
  Map,
  BarChart3,
  FileText,
  Bot,
  Settings,
  Clock,
  Droplets,
} from "lucide-react"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarRail,
  useSidebar,
} from "@/components/ui/sidebar"
import { ThemeToggle } from "@/components/ui/theme-toggle"

const sidebarItems = [
  {
    title: "Dashboard",
    url: "/dashboard",
    icon: LayoutDashboard,
    description: "Overview & situational awareness",
  },
  {
    title: "Predictions",
    url: "/ai-assistant",
    icon: Bot,
    description: "AI flood predictions & chat",
  },
  {
    title: "Flood Map",
    url: "/risk-map",
    icon: Map,
    description: "Interactive Cameroon flood map",
  },
  {
    title: "Reports",
    url: "/alerts",
    icon: FileText,
    description: "Community reports & alerts",
  },
  {
    title: "History",
    url: "/history",
    icon: Clock,
    description: "Historical flood analysis",
  },
  {
    title: "Analytics",
    url: "/analytics",
    icon: BarChart3,
    description: "Data trends & analysis",
  },
  {
    title: "Admin",
    url: "/settings",
    icon: Settings,
    description: "Settings & administration",
  },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const { state } = useSidebar()
  const isCollapsed = state === "collapsed"
  const location = useLocation()

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className={`border-b border-sidebar-border ${isCollapsed ? 'px-2 py-4' : 'px-4 py-4'}`}>
        <div className={`flex items-center ${isCollapsed ? 'justify-center' : 'gap-2.5'}`}>
          {/* Logo mark — circle with Droplets icon, matches STITCH brand */}
          <div className={`flex items-center justify-center rounded-full bg-[#1e3a8a] text-white flex-shrink-0 ${isCollapsed ? 'h-10 w-10' : 'h-9 w-9'}`}>
            <Droplets className={`${isCollapsed ? 'h-5 w-5' : 'h-4 w-4'}`} />
          </div>
          {!isCollapsed && (
            <div className="flex flex-col leading-tight">
              <span className="text-sm font-bold text-sidebar-foreground tracking-tight">
                AquaGuard AI
              </span>
              <span className="text-[10px] text-sidebar-foreground/55 font-medium">
                Cameroon Flood Intel
              </span>
            </div>
          )}
        </div>
      </SidebarHeader>

      <SidebarContent className="p-3">
        <SidebarMenu>
          {sidebarItems.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton
                asChild
                isActive={location.pathname === item.url}
                size="lg"
                className={`
                  ${isCollapsed
                    ? 'h-12 w-full justify-center p-3 mx-0 group-data-[collapsible=icon]:size-auto! group-data-[collapsible=icon]:w-full! group-data-[collapsible=icon]:h-12!'
                    : 'h-14 w-full justify-start gap-3 p-3'}
                  rounded-lg text-left hover:bg-sidebar-accent
                `}
                tooltip={isCollapsed ? item.title : undefined}
              >
                <Link to={item.url} className="flex items-center justify-center w-full">
                  <item.icon className={`shrink-0 ${isCollapsed ? 'h-5 w-5' : 'h-4 w-4'}`} />
                  {!isCollapsed && (
                    <div className="flex flex-col ml-3">
                      <span className="text-sm font-medium">{item.title}</span>
                      <span className="text-[10px] text-sidebar-foreground/55">
                        {item.description}
                      </span>
                    </div>
                  )}
                </Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarContent>

      <SidebarFooter className="p-3 border-t border-sidebar-border">
        {/* Emergency Alert button — matches STITCH */}
        {!isCollapsed && (
          <button className="w-full flex items-center justify-center gap-2 bg-red-600 hover:bg-red-700 text-white text-xs font-bold py-2.5 px-4 rounded-lg mb-3 transition-colors">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />
            Emergency Alert
          </button>
        )}
        <div className={`flex ${isCollapsed ? 'justify-center' : 'justify-between items-center'}`}>
          {!isCollapsed && (
            <div className="text-xs text-sidebar-foreground/50 space-y-0.5">
              <p className="font-medium">Settings</p>
              <p>Support</p>
            </div>
          )}
          <ThemeToggle size="sm" />
        </div>
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
