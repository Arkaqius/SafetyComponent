import { configurationHelp } from '../content/configurationHelp.js';
import { monitoringHelp } from './monitoringHelp.js';
import { systemHealthHelp } from './systemHealthHelp.js';

export const helpGroups = [
  { title: 'Monitorowanie domu', topics: monitoringHelp },
  {
    title: 'Diagnostyka i historia',
    topics: systemHealthHelp.map(topic => ({
      ...topic,
      route: topic.id === 'history' ? '/history' : `/functional-safety?tab=${topic.id.slice('health-'.length)}`,
    })),
  },
  {
    title: 'Konfiguracja instalacji',
    topics: configurationHelp.map(topic => ({
      ...topic,
      id: `config-${topic.id}`,
      route: `/configuration/${topic.id}`,
    })),
  },
];

const topics = helpGroups.flatMap(group => group.topics);
export type HelpTopic = (typeof topics)[number];

export function getHelpTopic(id: string | null): HelpTopic | undefined {
  return topics.find(topic => topic.id === id);
}

export function getViewHelp(pathname: string, search: string): HelpTopic | undefined {
  if (pathname === '/functional-safety') {
    const tab = new URLSearchParams(search).get('tab');
    return getHelpTopic(`health-${tab}`) ?? getHelpTopic('health-entities');
  }
  if (pathname === '/configuration' || pathname.startsWith('/configuration/')) {
    const page = pathname.split('/')[2];
    return getHelpTopic(`config-${page}`) ?? getHelpTopic('config-general');
  }
  return topics.find(topic => topic.route === pathname);
}

function searchText(value: string): string {
  return value
    .toLocaleLowerCase('pl')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .replace(/ł/g, 'l');
}

export function findHelpEntries(query: string) {
  const words = searchText(query).trim().split(/\s+/).filter(Boolean);
  return topics.flatMap(topic =>
    topic.entries
      .filter(entry => {
        const text = searchText(`${topic.title} ${entry.title} ${entry.text}`);
        return words.every(word => text.includes(word));
      })
      .map(entry => ({ topic, entry }))
  );
}
