import { simaiDecode } from './Scripts/decode.js';
import {
    audioManager,
    INTRO_TIMELINE,
    loadAllImages,
    parseMaidata,
    videoRender,
} from './Scripts/helper.js';
import { SimaiRenderer } from './Scripts/renderer.js';
import { loadUmengTransitionFrames, UMENG_TRANSITION_DURATION } from './transition.js';

const config = globalThis.__PYMAIVIEW_CONFIG__ || {};
const defaultSfxVolumes = {
    clock: 0.8, answer: 1, judge: 0.4, judge_ex: 0.4,
    judge_break: 0.4, judge_break_slide: 0.4, break: 0.4,
    slide: 0.4, break_slide: 0.4, break_slide_start: 0.4, touch: 0.4,
    touchHold_riser: 0.6, hanabi: 0.6,
};
const defaults = {
    speed: 6.5, touchSpeed: 7, slideSpeed: 0, middleDisplay: 1,
    moviebrightness: -3, showSensor: true, rotateStars: true,
    starRotationSpeed: 1,
    pinkStars: false, displayMode: 'simai', middleDistance: 0.25,
    effectDecayTime: 0.4, hanabiEffectDecayTime: 1.1, noteBaseSize: 11,
    maxSlideCount: 500, visualZoom: 200, slideIllegalRed: false,
    slideArrowHideBySensor: true, hideOutline: false, showUI: false,
    notPlayHoldEnd: false, drawHitEffect: true, drawHanabiEffect: true,
    renderSurroundingAuxiliaryText: true, backgroundColor: '#000',
    globalVolume: 0.65, musicVolume: 0.8, SfxVolume: 1,
    sfxVolumes: defaultSfxVolumes,
};
const requested = config.playback || {};
const settings = {
    ...defaults,
    ...requested,
    sfxVolumes: { ...defaultSfxVolumes, ...(requested.sfxVolumes || {}) },
};
const canvas = document.getElementById('main');

globalThis.__PYMAIVIEW_DOWNLOAD__ = async (blob) => {
    if (typeof globalThis.__pymaiview_chunk !== 'function') {
        throw new Error('缺少 pymaiview 输出接收器');
    }
    const chunkSize = 256 * 1024;
    const reader = blob.stream().getReader();
    try {
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            for (let offset = 0; offset < value.length; offset += chunkSize) {
                const end = Math.min(offset + chunkSize, value.length);
                let binary = '';
                for (let i = offset; i < end; i++) {
                    binary += String.fromCharCode(value[i]);
                }
                await globalThis.__pymaiview_chunk(btoa(binary));
            }
        }
    } finally {
        reader.releaseLock();
    }
    await globalThis.__pymaiview_done();
};

async function blobFrom(uri) {
    if (!uri) return null;
    const response = await fetch(uri);
    if (!response.ok) throw new Error(`资源加载失败 ${response.status}: ${uri}`);
    return response.blob();
}

async function imageFrom(uri) {
    const blob = await blobFrom(uri);
    if (!blob) return null;
    const image = new Image();
    image.src = URL.createObjectURL(blob);
    await image.decode();
    return image;
}

function isVideo(uri) {
    return /\.(mp4|webm|mov|mkv|avi|ogv)(?:[?#].*)?$/i.test(uri || '');
}

async function videoFrom(uri) {
    if (!uri) return null;
    const video = document.createElement('video');
    video.src = uri;
    video.muted = true;
    video.preload = 'auto';
    await new Promise((resolve, reject) => {
        video.addEventListener('loadedmetadata', resolve, { once: true });
        video.addEventListener('error', () => reject(new Error(`背景视频加载失败: ${uri}`)), { once: true });
    });
    return video;
}

async function loadRenderFonts() {
    if (!document.fonts) return;
    const fonts = [
        ['16px combo', '0123456789'],
        ['16px mono', '0123456789'],
        ['16px title', '谱面 ABC 0123'],
        ['16px Minimoon', 'METER BPM'],
        ['16px RodinUIHeader', 'METER BPM 0123'],
        ['16px RodinUIValue', '0123456789'],
        ['bold 16px RodinUILabel', 'CRITICAL PERFECT'],
        ['400 16px "Google Sans"', 'MASTER NOTES DESIGNER'],
        ['700 16px "Google Sans"', 'MASTER LV 14+'],
    ];
    const loaded = await Promise.all(fonts.map(([spec, text]) => document.fonts.load(spec, text)));
    const missing = fonts
        .filter((_, index) => loaded[index].length === 0)
        .map(([spec]) => spec);
    if (missing.length) throw new Error(`字体加载失败: ${missing.join(', ')}`);
    await document.fonts.ready;
}

const ready = (async () => {
    await loadRenderFonts();
    const [images] = await Promise.all([loadAllImages(), audioManager.init()]);
    audioManager.setGlobalVolume(settings.globalVolume);
    audioManager.setBGMVolume(settings.musicVolume);
    audioManager.setSFXVolume(settings.SfxVolume);
    audioManager.setSFXVolumes(settings.sfxVolumes);
    return images;
})();

async function render(request = {}) {
    const images = await ready;
    const maidata = parseMaidata(config.maidata || '');
    const difficulty = Number(request.difficulty ?? config.difficulty ?? 5);
    const chart = maidata[`inote_${difficulty}`];
    if (!chart) throw new Error(`maidata 中没有 inote_${difficulty}`);

    const decoded = simaiDecode(chart, 0);
    if (decoded.failed) throw new Error('谱面解析失败');

    const notesCounts = decoded.notesCounts || { tap: 0, hold: 0, slide: 0, touch: 0, break: 0 };
    const score = Number(decoded.score || 0);
    const playScoreRes = {
        ...notesCounts,
        score,
        breakScore: notesCounts.break ? 1 / notesCounts.break : 0,
        invScore: score ? 1 / score : 0,
    };

    const music = await blobFrom(config.music);
    if (music) {
        await audioManager.setBackgroundMusic(music);
        if (!audioManager.haveBGM()) throw new Error('背景音乐解码失败');
    }

    const background = config.pv
        ? (isVideo(config.pv) ? await videoFrom(config.pv) : await imageFrom(config.pv))
        : null;
    const width = Number(request.width || 1280);
    const height = Number(request.height || 720);
    const fps = Number(request.fps || 30);
    const start = Number(request.start || 0);
    const maxEnd = Math.max(decoded.endTime, audioManager.getBGMDuration()) + 1;
    const end = request.end == null ? maxEnd : Number(request.end);
    if (end <= start) throw new Error('end 必须大于 start');

    canvas.width = width;
    canvas.height = height;
    const renderer = new SimaiRenderer(canvas, settings);
    if (settings.scale != null) renderer.scale = Number(settings.scale);
    renderer.setImages(images);
    renderer.setJudgeEvents((decoded.notes || [])
        .filter((note) => note.type === 'tap' || note.type === 'hold')
        .map((note) => ({
            time: Number(note.time) + (note.type === 'hold' ? Number(note.holdDuration || 0) : 0),
            pos: Number(note.pos),
            kind: note.isMine ? 'miss' : (note.isBreak ? 'break' : 'perfect'),
        }))
        .filter((event) => Number.isFinite(event.time) && Number.isInteger(event.pos) && event.pos >= 1 && event.pos <= 8));
    if (request.includeIntro !== false) {
        if (INTRO_TIMELINE.transition !== UMENG_TRANSITION_DURATION) {
            throw new Error('入场时间轴与乌蒙转场素材时长不一致');
        }
        renderer.setTransitionFrames(
            await loadUmengTransitionFrames(fps, Math.min(512, width, height)),
            fps,
        );
    }

    const bpmEvents = (decoded.tags || [])
        .filter((tag) => tag.type === 'bpm' && Number(tag.value) > 0)
        .map((tag) => ({ time: Number(tag.time) || 0, value: Number(tag.value) }))
        .sort((a, b) => a.time - b.time);
    const chartInfo = {
        title: maidata.title || '',
        artist: maidata.artist || '-',
        des: maidata[`des_${difficulty}`] || maidata.des || '-',
        lv: maidata[`lv_${difficulty}`] || '0',
        difficulty,
        bpm: Number(maidata.wholebpm) || Number(decoded.bpm) || 0,
        bpmEvents,
    };
    renderer.chartInfo = chartInfo;
    try {
        await videoRender(audioManager, canvas, renderer, {
            start,
            end,
            fps,
            width,
            height,
            bgmVolume: request.bgmVolume ?? settings.musicVolume,
            sfxVolume: request.sfxVolume ?? settings.SfxVolume,
            includeAudio: request.includeAudio !== false,
            includeBgm: request.includeAudio !== false && !!music,
            includeSfx: request.includeSfx !== false,
            includeIntro: request.includeIntro !== false,
            introDuration: INTRO_TIMELINE.total,
            includeAllPerfect: request.includeAllPerfect === true,
            musicDelay: Number(maidata.first || 0),
            editorBackgroundImage: background instanceof HTMLImageElement ? background : null,
            editorBackgroundVideo: background instanceof HTMLVideoElement ? background : null,
            notes: decoded.notes,
            playScoreRes,
            chartInfo,
        });
    } finally {
        renderer.disposeTransitionFrames();
    }
    return { start, end, frames: Math.ceil((end - start) * fps) };
}

globalThis.pymaiview = { ready, render };
