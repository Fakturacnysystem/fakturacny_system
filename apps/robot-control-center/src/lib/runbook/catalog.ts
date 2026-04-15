import type { RunbookContract } from "@/types/contracts";

export const runbookCatalog: RunbookContract = {
  severities: [
    {
      severity: "SEV-1",
      examples: [
        "Treba okamžite uzavrieť otvorené riziko.",
        "Vykonávanie je v nebezpečnom stave alebo je poškodený stav ovládania.",
        "Kritický rozpor medzi backendom a runtime stavom.",
      ],
    },
    {
      severity: "SEV-2",
      examples: [
        "Staré trhové dáta, ktoré môžu ovplyvniť vykonanie.",
        "Zhoršená spoľahlivosť alebo opakované chyby medzi bridge a backendom.",
        "Väčší rozpor v histórii alebo vo forenznej kontrole.",
      ],
    },
    {
      severity: "SEV-3",
      examples: [
        "Len čiastočne dostupné artefakty.",
        "Menej závažné zhoršenie diagnostiky.",
        "Nesúlad medzi UI a bridge bez priameho rizika vykonania.",
      ],
    },
  ],
  procedures: [
    {
      title: "Pozastaviť",
      whenToUse: ["Podozrivé správanie", "Pred údržbou", "Manuálna kontrola"],
      steps: [
        "Potvrď pozastavenie pod menom konkrétneho operátora.",
        "Skontroluj, že runtime vrátil nový stav aj auditnú referenciu.",
        "Ak ide o prevádzkový dôvod, doplň poznámku k incidentu.",
      ],
    },
    {
      title: "Pokračovať",
      whenToUse: ["Stav systému je prijateľný", "Kritické blokácie sú odstránené"],
      steps: [
        "Skontroluj, že zdravie systému nie je v nebezpečnom stave.",
        "Skontroluj, že blokácie sú vysvetlené alebo odstránené.",
        "Pred pokračovaním zapíš jasný dôvod, prečo sa systém znovu púšťa.",
      ],
    },
    {
      title: "Zmraziť",
      whenToUse: ["Spoľahlivosť systému je nejasná", "Treba okamžitý zásah človeka"],
      steps: [
        "Okamžite zastav nové otvorenia.",
        "Otvor diagnostiku a ulož balík dôkazov.",
        "Ak nejasnosť trvá, prejdite na spätnú kontrolu histórie.",
      ],
    },
    {
      title: "Núdzovo zavrieť",
      whenToUse: ["Treba okamžite ukončiť pozície", "Expozícia je neprijateľná"],
      steps: [
        "Potvrď odpoveď na núdzové zatvorenie aj auditnú referenciu.",
        "Otvor diagnostiku a ulož vstupy pre spätnú kontrolu.",
        "Zapíš poznámku s menom operátora, časom, zásahom a ďalším krokom kontroly.",
      ],
    },
  ],
  replayChecklist: [
    "Otvor laboratórium histórie.",
    "Skontroluj časovú os behu, incidenty a podobné situácie.",
    "Pozri si alternatívne scenáre a rozpad výsledku.",
    "Zapíš predpokladanú hlavnú príčinu.",
    "Urči závažnosť a navrhni nápravný krok.",
  ],
};
