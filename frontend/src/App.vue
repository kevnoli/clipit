<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

import { defaultLocale, getMessage, localeOptions, resolveLocale } from "./i18n";

const me = ref(null);
const notice = ref(null);
const ready = ref(false);
const saving = ref(false);
const actionBusy = ref("");
const showDisconnectModal = ref(false);
const commandInput = ref(null);
const autoSaveState = ref("idle");
let noticeTimeoutId = null;
let autoSaveTimeoutId = null;
let hydratingForm = false;
let lastSavedSignature = "";
const storedLocale =
    typeof window !== "undefined" ? window.localStorage.getItem("clipit-locale") : null;
const locale = ref(
    resolveLocale(
        storedLocale || (typeof navigator !== "undefined" ? navigator.language : defaultLocale),
    ),
);

const permissionOptions = ["Everyone", "Subscriber", "VIP", "Moderator", "Owner"];
const permissionKeys = {
    Everyone: "everyone",
    Subscriber: "subscriber",
    VIP: "vip",
    Moderator: "moderator",
    Owner: "owner",
};

function createDefaultForm() {
    return {
        commands: ["!clipit"],
        commandDraft: "",
        minimumVotes: 2,
        commandWindow: 15,
        commandCooldown: 30,
        votePermission: "Everyone",
        overridePermission: "Owner",
        subscriberMonths: 3,
        webhookUrl: "",
        clearDiscordWebhook: false,
        denylistText: "",
    };
}

const form = ref(createDefaultForm());

function t(path, params = {}) {
    const template = getMessage(locale.value, path);
    if (typeof template !== "string") {
        return path;
    }

    return template.replace(/\{(\w+)\}/g, (_, key) => String(params[key] ?? `{${key}}`));
}

const signedIn = computed(() => Boolean(me.value));
const broadcasterId = computed(() => me.value?.broadcaster_id ?? "");
const enableActionLabel = computed(() =>
    me.value?.enabled ? t("manage.disableButton") : t("manage.enableButton"),
);
const enableActionHint = computed(() =>
    me.value?.enabled
        ? t("manage.disableHint")
        : t("manage.enableHint"),
);
const scrollIndicatorLabel = computed(() =>
    signedIn.value ? t("hero.scrollToSettings") : t("hero.scrollToConnect"),
);
const showVoteWindow = computed(() => Number(form.value.minimumVotes) > 1);
const showOverridePermission = computed(() => Number(form.value.minimumVotes) > 1);
const subscriberMonthsPlacement = computed(() => {
    if (form.value.votePermission === "Subscriber") {
        return "vote";
    }

    if (showOverridePermission.value && form.value.overridePermission === "Subscriber") {
        return "override";
    }

    return null;
});
const webhookConfigured = computed(() => Boolean(me.value?.settings?.discord_webhook_configured));
const autoSaveMessage = computed(() => {
    if (!signedIn.value) {
        return "";
    }
    if (saving.value || autoSaveState.value === "saving") {
        return t("manage.autosaveSaving");
    }
    if (autoSaveState.value === "saved") {
        return t("manage.autosaveSaved");
    }
    if (autoSaveState.value === "error") {
        return t("manage.autosaveError");
    }
    if (autoSaveState.value === "pending") {
        return t("manage.autosavePending");
    }
    return t("manage.autosaveIdle");
});
const showReconnectAction = computed(() => Boolean(me.value?.worker?.worker_error));
const permissionLabels = computed(() =>
    Object.fromEntries(
        permissionOptions.map((option) => [option, t(`permissions.${permissionKeys[option]}`)]),
    ),
);
const workerIndicator = computed(() => {
    const workerError = me.value?.worker?.worker_error;
    const workerRunning = Boolean(me.value?.worker?.worker_running);

    return {
        value: workerError
            ? t("status.errored")
            : workerRunning
              ? t("status.running")
              : t("status.idle"),
        tone: workerError ? "error" : workerRunning ? "ok" : "idle",
        hint: workerError ? t("status.workerErrorHint") : "",
    };
});

async function requestJson(url, options = {}) {
    const headers = {
        Accept: "application/json",
        ...(options.headers || {}),
    };

    if (options.body !== undefined) {
        headers["Content-Type"] = "application/json";
    }

    const method = (options.method || "GET").toUpperCase();
    if (!["GET", "HEAD"].includes(method)) {
        const csrfToken = readCookie("clipit_csrf");
        if (csrfToken) {
            headers["X-CSRF-Token"] = csrfToken;
        }
    }

    const response = await fetch(url, {
        credentials: "same-origin",
        ...options,
        method,
        headers,
        body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });

    if (response.status === 401) {
        return null;
    }

    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json") ? await response.json() : null;

    if (!response.ok) {
        const detail =
            payload && typeof payload === "object" && "detail" in payload
                ? String(payload.detail)
                : `Request failed for ${url}: ${response.status}`;
        throw new Error(detail);
    }

    return payload;
}

function readCookie(name) {
    const cookies = document.cookie.split(";").map((part) => part.trim());
    const match = cookies.find((part) => part.startsWith(`${name}=`));
    return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : "";
}

function normalizePermission(value, fallback) {
    const normalized = (value || fallback).trim().toLowerCase();
    if (normalized.startsWith("sub:")) {
        return "Subscriber";
    }

    return permissionOptions.find((option) => option.toLowerCase() === normalized) || fallback;
}

function extractSubscriberMonths(value) {
    if (!value || !value.startsWith("SUB:")) {
        return 3;
    }

    const parsed = Number.parseInt(value.split(":")[1] || "3", 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 3;
}

function splitList(value) {
    return value
        .split(/[\n,]+/)
        .map((item) => item.trim())
        .filter(Boolean);
}

function normalizeCommand(value) {
    const next = value.trim();
    if (!next) {
        return "";
    }

    return next.startsWith("!") ? next : `!${next}`;
}

function addCommand(value) {
    const next = normalizeCommand(value);
    if (!next) {
        return;
    }

    const existing = form.value.commands.map((command) => command.toLowerCase());
    if (existing.includes(next.toLowerCase())) {
        form.value.commandDraft = "";
        return;
    }

    form.value.commands = [...form.value.commands, next];
    form.value.commandDraft = "";
}

function removeCommand(commandToRemove) {
    form.value.commands = form.value.commands.filter((command) => command !== commandToRemove);
}

function commitCommandDraft() {
    if (!form.value.commandDraft.trim()) {
        return;
    }

    addCommand(form.value.commandDraft);
}

function handleCommandKeydown(event) {
    if (!["Enter", ",", "Tab"].includes(event.key)) {
        return;
    }

    if (!form.value.commandDraft.trim()) {
        return;
    }

    event.preventDefault();
    addCommand(form.value.commandDraft);
}

function buildSettingsPayload() {
    return {
        commands: form.value.commands,
        minimum_votes: Number(form.value.minimumVotes),
        command_window: Number(form.value.commandWindow),
        command_cooldown: Number(form.value.commandCooldown),
        vote_permissions: form.value.votePermission,
        subscriber_months: `SUB:${Number(form.value.subscriberMonths) || 3}`,
        override_permissions: form.value.overridePermission,
        discord_webhook_url: form.value.webhookUrl.trim() || null,
        clear_discord_webhook: form.value.clearDiscordWebhook,
        donotallowlist_enabled: splitList(form.value.denylistText).length > 0,
        donotallowlist_usernames: splitList(form.value.denylistText),
    };
}

function getFormSignature() {
    return JSON.stringify(buildSettingsPayload());
}

function populateForm(snapshot) {
    const settings = snapshot?.settings;
    hydratingForm = true;
    if (!settings) {
        form.value = createDefaultForm();
        lastSavedSignature = getFormSignature();
        autoSaveState.value = "idle";
        hydratingForm = false;
        return;
    }

    form.value = {
        commands: [...(settings.commands || [])],
        commandDraft: "",
        minimumVotes: settings.minimum_votes ?? 2,
        commandWindow: settings.command_window ?? 15,
        commandCooldown: settings.command_cooldown ?? 30,
        votePermission: normalizePermission(settings.vote_permissions, "Everyone"),
        overridePermission: normalizePermission(settings.override_permissions, "Owner"),
        subscriberMonths: extractSubscriberMonths(settings.subscriber_months),
        webhookUrl: "",
        clearDiscordWebhook: false,
        denylistText: (settings.donotallowlist_usernames || []).join("\n"),
    };
    lastSavedSignature = getFormSignature();
    autoSaveState.value = "idle";
    hydratingForm = false;
}

async function refreshState() {
    try {
        const snapshot = await requestJson("/api/me");
        me.value = snapshot;
        populateForm(snapshot);
    } catch (error) {
        console.error(error);
    }
}

function sleep(ms) {
    return new Promise((resolve) => {
        window.setTimeout(resolve, ms);
    });
}

async function logout() {
    actionBusy.value = "logout";
    try {
        await requestJson("/api/auth/logout", {
            method: "POST",
        });
        me.value = null;
        form.value = createDefaultForm();
        window.location.assign("/");
    } finally {
        actionBusy.value = "";
    }
}

function reconnectBroadcaster() {
    window.location.assign("/api/auth/twitch/login");
}

async function saveSettings({ fromAutosave = false } = {}) {
    if (!broadcasterId.value) {
        return;
    }

    saving.value = true;
    autoSaveState.value = "saving";
    try {
        if (!form.value.commands.length) {
            throw new Error(t("form.validationAddCommand"));
        }

        const response = await requestJson(`/api/broadcasters/${broadcasterId.value}/settings`, {
            method: "PUT",
            body: buildSettingsPayload(),
        });

        me.value = {
            ...me.value,
            settings: response.settings,
        };
        lastSavedSignature = getFormSignature();
        autoSaveState.value = "saved";
        if (!fromAutosave) {
            notice.value = {
                tone: "success",
                message: t("notice.settingsSaved"),
            };
        }
    } catch (error) {
        autoSaveState.value = "error";
        notice.value = {
            tone: "error",
            message: error instanceof Error ? error.message : t("notice.saveFailed"),
        };
    } finally {
        saving.value = false;
    }
}

async function toggleEnabled() {
    if (!broadcasterId.value || !me.value) {
        return;
    }

    actionBusy.value = "toggle";
    try {
        if (me.value.enabled) {
            await requestJson(`/api/broadcasters/${broadcasterId.value}/disable`, {
                method: "POST",
            });
            await refreshState();
            notice.value = {
                tone: "success",
                message: t("notice.workerDisabled"),
            };
        } else {
            const snapshot = await requestJson(`/api/broadcasters/${broadcasterId.value}/enable`, {
                method: "POST",
            });
            me.value = snapshot;
            populateForm(snapshot);
            await sleep(900);
            await refreshState();

            if (me.value?.worker?.worker_error || !me.value?.enabled) {
                notice.value = {
                    tone: "error",
                    message: t("notice.workerReconnectRequired"),
                };
            } else {
                notice.value = {
                    tone: "success",
                    message: t("notice.workerEnabled"),
                };
            }
        }
    } catch (error) {
        await refreshState();
        notice.value = {
            tone: "error",
            message:
                error instanceof Error ? error.message : t("notice.workerReconnectRequired"),
        };
    } finally {
        actionBusy.value = "";
    }
}

async function disconnectBroadcaster() {
    if (!broadcasterId.value) {
        return;
    }

    actionBusy.value = "disconnect";
    try {
        await requestJson(`/api/broadcasters/${broadcasterId.value}`, {
            method: "DELETE",
        });
        me.value = null;
        form.value = createDefaultForm();
        notice.value = {
            tone: "success",
            message: t("notice.broadcasterDisconnected"),
        };
        window.location.assign("/");
    } catch (error) {
        notice.value = {
            tone: "error",
            message:
                error instanceof Error ? error.message : t("notice.broadcasterDisconnectFailed"),
        };
    } finally {
        actionBusy.value = "";
    }
}

function openDisconnectModal() {
    showDisconnectModal.value = true;
}

function closeDisconnectModal() {
    if (actionBusy.value === "disconnect") {
        return;
    }

    showDisconnectModal.value = false;
}

function setNoticeFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const channel = params.get("channel");
    const auth = params.get("auth");
    const message = params.get("message");

    if (connected) {
        notice.value = {
            tone: "success",
            message: channel
                ? t("notice.connectedWithChannel", { channel })
                : t("notice.connected"),
        };
    } else if (auth === "error") {
        notice.value = {
            tone: "error",
            message: message || t("notice.authFailed"),
        };
    }

    if (connected || auth) {
        const cleanUrl = `${window.location.pathname}${window.location.hash}`;
        window.history.replaceState({}, "", cleanUrl);
    }
}

function dismissNotice() {
    notice.value = null;
}

function bindRevealObserver() {
    const observer = new IntersectionObserver(
        (entries) => {
            for (const entry of entries) {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                }
            }
        },
        {
            threshold: 0.2,
        },
    );

    document.querySelectorAll(".reveal").forEach((node) => observer.observe(node));
}

watch(
    () => form.value.webhookUrl,
    (value) => {
        if (value.trim()) {
            form.value.clearDiscordWebhook = false;
        }
    },
);

watch(locale, (value) => {
    if (typeof window !== "undefined") {
        window.localStorage.setItem("clipit-locale", value);
    }
});

watch(
    () => getFormSignature(),
    (signature) => {
        if (!signedIn.value || hydratingForm) {
            return;
        }

        if (signature === lastSavedSignature) {
            if (autoSaveState.value !== "saved") {
                autoSaveState.value = "idle";
            }
            return;
        }

        if (autoSaveTimeoutId) {
            window.clearTimeout(autoSaveTimeoutId);
        }

        autoSaveState.value = "pending";
        autoSaveTimeoutId = window.setTimeout(() => {
            saveSettings({ fromAutosave: true });
            autoSaveTimeoutId = null;
        }, 1000);
    },
);

watch(notice, (value) => {
    if (noticeTimeoutId) {
        window.clearTimeout(noticeTimeoutId);
        noticeTimeoutId = null;
    }

    if (!value) {
        return;
    }

    noticeTimeoutId = window.setTimeout(() => {
        notice.value = null;
        noticeTimeoutId = null;
    }, 4500);
});

onMounted(async () => {
    setNoticeFromUrl();
    await refreshState();
    bindRevealObserver();

    requestAnimationFrame(() => {
        ready.value = true;
    });
});

onUnmounted(() => {
    if (noticeTimeoutId) {
        window.clearTimeout(noticeTimeoutId);
    }
    if (autoSaveTimeoutId) {
        window.clearTimeout(autoSaveTimeoutId);
    }
});
</script>

<template>
    <div class="site-shell" :class="{ 'is-ready': ready }">
        <div class="ambient ambient-a"></div>
        <div class="ambient ambient-b"></div>

        <header class="site-header">
            <a class="wordmark" href="/">
                <span class="wordmark-mark" aria-hidden="true">
                    <svg viewBox="0 0 48 48" role="presentation">
                        <rect x="8" y="12" width="28" height="24" rx="7" />
                        <path d="M16 8v8M28 8v8M36 20l8-4v16l-8-4" />
                        <path d="M14 24h12" />
                    </svg>
                </span>
                <span>Clipit</span>
            </a>

            <label class="language-select">
                <span class="sr-only">{{ t("header.languageLabel") }}</span>
                <select v-model="locale" :aria-label="t('header.languageLabel')">
                    <option
                        v-for="option in localeOptions"
                        :key="option.code"
                        :value="option.code"
                    >
                        {{ option.label }}
                    </option>
                </select>
            </label>
        </header>

        <main>
            <section class="hero">
                <div class="hero-copy reveal">
                    <h1>{{ t("hero.title") }}</h1>
                    <p class="hero-body">{{ t("hero.body") }}</p>
                </div>

                <div class="hero-scroll reveal">
                    <a class="button button-secondary scroll-cta" href="#status">
                        <span>{{ scrollIndicatorLabel }}</span>
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                            <path d="M12 5v13" />
                            <path d="M7 13l5 5 5-5" />
                        </svg>
                    </a>
                </div>
            </section>

            <section v-if="notice" class="notice-strip" aria-live="polite">
                <p :data-tone="notice.tone">{{ notice.message }}</p>
                <button type="button" @click="dismissNotice" :aria-label="t('notice.dismiss')">
                    {{ t("notice.dismiss") }}
                </button>
            </section>

            <section id="status" class="status-band reveal">
                <div class="section-heading">
                    <p class="eyebrow">{{ t("status.eyebrow") }}</p>
                    <h2>{{ t("status.title") }}</h2>
                </div>

                <div class="status-layout">
                    <div class="status-panel" :data-auth="signedIn ? 'yes' : 'no'">
                        <template v-if="signedIn">
                            <div class="status-row full status-headline">
                                <div class="status-identity">
                                    <label>{{ t("status.signedInAs") }}</label>
                                    <strong>{{ me.display_name || me.login }}</strong>
                                </div>

                                <div
                                    class="status-led status-led-inline"
                                    :data-tone="workerIndicator.tone"
                                    :title="workerIndicator.hint"
                                >
                                    <span class="status-led-light" aria-hidden="true"></span>
                                    <strong>{{ workerIndicator.value }}</strong>
                                </div>
                            </div>

                            <form class="settings-grid full" @submit.prevent>
                                <div class="field span-2">
                                    <label for="commands">{{ t("form.commands") }}</label>
                                    <div class="chip-input" @click="commandInput?.focus()">
                                        <span v-for="command in form.commands" :key="command" class="chip">
                                            <span>{{ command }}</span>
                                            <button type="button" class="chip-remove" :aria-label="t('form.removeCommand', { command })"
                                                @click.stop="removeCommand(command)">
                                                x
                                            </button>
                                        </span>
                                        <input id="commands" ref="commandInput" v-model="form.commandDraft" type="text"
                                            autocomplete="off" spellcheck="false" :placeholder="t('form.commandsPlaceholder')"
                                            @keydown="handleCommandKeydown" @blur="commitCommandDraft" />
                                    </div>
                                    <p>{{ t("form.commandsHint") }}</p>
                                </div>

                                <div class="field">
                                    <label for="minimumVotes">{{ t("form.minimumVotes") }}</label>
                                    <input id="minimumVotes" v-model.number="form.minimumVotes" type="number" min="1" />
                                </div>

                                <div v-if="showVoteWindow" class="field">
                                    <label for="commandWindow">{{ t("form.commandWindow") }}</label>
                                    <input id="commandWindow" v-model.number="form.commandWindow" type="number"
                                        min="1" />
                                </div>

                                <div class="field">
                                    <label for="commandCooldown">{{ t("form.commandCooldown") }}</label>
                                    <input id="commandCooldown" v-model.number="form.commandCooldown" type="number"
                                        min="0" />
                                </div>

                                <div class="field permission-field">
                                    <div
                                        class="permission-cluster"
                                        :class="{
                                            'has-subscriber-inline': subscriberMonthsPlacement === 'vote',
                                        }"
                                    >
                                        <div class="field compact-field">
                                            <label for="votePermission">{{ t("form.votePermission") }}</label>
                                            <select id="votePermission" v-model="form.votePermission">
                                                <option v-for="option in permissionOptions" :key="`vote-${option}`"
                                                    :value="option">
                                                    {{ permissionLabels[option] }}
                                                </option>
                                            </select>
                                        </div>
                                        <div
                                            v-if="subscriberMonthsPlacement === 'vote'"
                                            class="field compact-field subscriber-inline"
                                        >
                                            <label for="subscriberMonthsVote">
                                                {{ t("form.subscriberMonths") }}
                                            </label>
                                            <input
                                                id="subscriberMonthsVote"
                                                v-model.number="form.subscriberMonths"
                                                type="number"
                                                min="1"
                                            />
                                        </div>
                                    </div>
                                    <p v-if="subscriberMonthsPlacement === 'vote'">
                                        {{ t("form.subscriberMonthsHint") }}
                                    </p>
                                </div>

                                <div v-if="showOverridePermission" class="field permission-field">
                                    <div
                                        class="permission-cluster"
                                        :class="{
                                            'has-subscriber-inline':
                                                subscriberMonthsPlacement === 'override',
                                        }"
                                    >
                                        <div class="field compact-field">
                                            <label for="overridePermission">{{ t("form.overridePermission") }}</label>
                                            <select id="overridePermission" v-model="form.overridePermission">
                                                <option v-for="option in permissionOptions" :key="`override-${option}`"
                                                    :value="option">
                                                    {{ permissionLabels[option] }}
                                                </option>
                                            </select>
                                        </div>
                                        <div
                                            v-if="subscriberMonthsPlacement === 'override'"
                                            class="field compact-field subscriber-inline"
                                        >
                                            <label for="subscriberMonthsOverride">
                                                {{ t("form.subscriberMonths") }}
                                            </label>
                                            <input
                                                id="subscriberMonthsOverride"
                                                v-model.number="form.subscriberMonths"
                                                type="number"
                                                min="1"
                                            />
                                        </div>
                                    </div>
                                    <p v-if="subscriberMonthsPlacement === 'override'">
                                        {{ t("form.subscriberMonthsHint") }}
                                    </p>
                                </div>

                                <div class="field span-2">
                                    <label for="webhookUrl">{{ t("form.webhook") }}</label>
                                    <input id="webhookUrl" v-model="form.webhookUrl" type="url" autocomplete="off"
                                        spellcheck="false" :placeholder="t('form.webhookPlaceholder')" />
                                    <p v-if="webhookConfigured">
                                        {{ t("form.webhookStored") }}
                                    </p>
                                    <p v-else>{{ t("form.webhookOptional") }}</p>
                                </div>

                                <label v-if="webhookConfigured" class="toggle span-2">
                                    <span class="toggle-copy">{{ t("form.clearWebhook") }}</span>
                                    <input v-model="form.clearDiscordWebhook" class="toggle-checkbox" type="checkbox" />
                                </label>

                                <div class="field span-2">
                                    <label for="denylist">{{ t("form.blockedUsernames") }}</label>
                                    <textarea id="denylist" v-model="form.denylistText" rows="5" spellcheck="false"
                                        :placeholder="t('form.blockedUsernamesPlaceholder')"></textarea>
                                    <p>{{ t("form.blockedUsernamesHint") }}</p>
                                </div>

                            </form>

                            <section class="manage-panel full" aria-label="Manage broadcaster">
                                <div class="manage-head">
                                    <div class="manage-copy">
                                        <label>{{ t("manage.label") }}</label>
                                        <strong>{{ t("manage.title") }}</strong>
                                    </div>
                                    <div class="manage-status">
                                        <span class="autosave-state">{{ autoSaveMessage }}</span>
                                        <button class="icon-button" type="button" :aria-label="t('manage.refresh')"
                                            :title="t('manage.refresh')" @click="refreshState">
                                            <svg viewBox="0 0 20 20" aria-hidden="true">
                                                <path d="M15.9 6.7A6.5 6.5 0 1 0 16.5 10" fill="none" />
                                                <path d="M16 3.8v3.8h-3.8" fill="none" />
                                            </svg>
                                        </button>
                                    </div>
                                </div>

                                <div class="manage-actions">
                                    <div class="manage-action-item">
                                        <span class="manage-action-label">{{ enableActionHint }}</span>
                                        <button class="button button-secondary" type="button"
                                            :disabled="actionBusy === 'toggle'" @click="toggleEnabled">
                                            {{ actionBusy === "toggle" ? t("manage.updating") : enableActionLabel }}
                                        </button>
                                    </div>

                                    <div v-if="showReconnectAction" class="manage-action-item">
                                        <span class="manage-action-label">{{ t("manage.reconnectHint") }}</span>
                                        <button class="button button-secondary" type="button"
                                            @click="reconnectBroadcaster">
                                            {{ t("manage.reconnectButton") }}
                                        </button>
                                    </div>

                                    <div class="manage-action-item">
                                        <span class="manage-action-label">{{ t("manage.logoutHint") }}</span>
                                        <button class="button button-secondary" type="button"
                                            :disabled="actionBusy === 'logout'" @click="logout">
                                            {{ actionBusy === "logout" ? t("manage.logoutBusy") : t("manage.logoutButton") }}
                                        </button>
                                    </div>

                                    <div class="manage-action-item">
                                        <span class="manage-action-label manage-action-label-danger">{{ t("manage.removeHint") }}</span>
                                        <button class="button button-danger" type="button"
                                            :disabled="actionBusy === 'disconnect'" @click="openDisconnectModal">
                                            {{ t("manage.removeButton") }}
                                        </button>
                                    </div>
                                </div>
                            </section>
                        </template>

                        <template v-else>
                            <div class="status-row full">
                                <label>{{ t("status.waiting") }}</label>
                                <strong>{{ t("status.noSession") }}</strong>
                            </div>
                            <div class="status-row full">
                                <label>{{ t("status.whatHappens") }}</label>
                                <strong>{{ t("status.connectExplanation") }}</strong>
                            </div>
                            <div class="status-row full">
                                <label>{{ t("status.triggering") }}</label>
                                <strong>{{ t("status.triggeringExplanation") }}</strong>
                            </div>
                            <div class="status-actions full">
                                <a class="button button-primary" href="/api/auth/twitch/login">
                                    {{ t("status.connectButton") }}
                                </a>
                            </div>
                        </template>
                    </div>
                </div>
            </section>
        </main>

        <div v-if="showDisconnectModal" class="modal-backdrop" role="presentation" @click="closeDisconnectModal">
            <section class="modal-card" role="dialog" aria-modal="true" aria-labelledby="remove-broadcaster-title"
                @click.stop>
                <p class="eyebrow">{{ t("modal.eyebrow") }}</p>
                <h2 id="remove-broadcaster-title">{{ t("modal.title") }}</h2>
                <p class="modal-copy">{{ t("modal.copy") }}</p>
                <div class="modal-actions">
                    <button class="button button-secondary" type="button" @click="closeDisconnectModal">
                        {{ t("modal.keep") }}
                    </button>
                    <button class="button button-danger" type="button" :disabled="actionBusy === 'disconnect'"
                        @click="disconnectBroadcaster">
                        {{ actionBusy === "disconnect" ? t("manage.removeBusy") : t("manage.removeButton") }}
                    </button>
                </div>
            </section>
        </div>
    </div>
</template>
