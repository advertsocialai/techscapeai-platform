/** Live targets for the Klara-ai branch. Previews sit behind Vercel SSO;
 *  the _vercel_share token is exchanged for a cookie in global-setup. */
export const TARGETS = {
  klara: {
    name: 'Klara app (customer-app)',
    base: 'https://klara-customer-app-git-klara-ai-advertsocialais-projects.vercel.app',
    share: process.env.KLARA_SHARE || 'vBAe28rFX2WlWKHV0Xg9dSwqGct4PrvR',
  },
  agency: {
    name: 'Agency dashboard',
    base: 'https://agency-dashboard-git-klara-ai-advertsocialais-projects.vercel.app',
    share: process.env.AGENCY_SHARE || 'jD4tBtY7EqbOpbG1cdYBDQ05TVuxuzQ2',
  },
  platform: {
    name: 'Techscape AI platform (API)',
    base: 'https://techscapeai-platform-git-klara-ai-advertsocialais-projects.vercel.app',
    share: process.env.PLATFORM_SHARE || 'bEaWONQvNhBekb1AYmcJkU3XbegkHlE4',
  },
} as const

export type TargetKey = keyof typeof TARGETS
