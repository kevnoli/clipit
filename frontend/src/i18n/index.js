import en from "./locales/en";
import es from "./locales/es";
import ptBR from "./locales/pt-BR";

export const defaultLocale = "en";

export const messages = {
    en,
    "pt-BR": ptBR,
    es,
};

export const localeOptions = [
    { code: "en", label: en.languageOptions.en, name: en.languageName },
    { code: "pt-BR", label: en.languageOptions["pt-BR"], name: ptBR.languageName },
    { code: "es", label: en.languageOptions.es, name: es.languageName },
];

export function resolveLocale(candidate) {
    if (!candidate) {
        return defaultLocale;
    }

    const normalized = candidate.toLowerCase();

    if (normalized.startsWith("pt")) {
        return "pt-BR";
    }

    if (normalized.startsWith("es")) {
        return "es";
    }

    if (normalized.startsWith("en")) {
        return "en";
    }

    return defaultLocale;
}

export function getMessage(locale, path) {
    return path.split(".").reduce((value, key) => value?.[key], messages[locale] ?? messages[defaultLocale]);
}
