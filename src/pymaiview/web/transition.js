// Direct extraction of the playback pipeline in umeng_web_color_demo.html.
// The animation frames and the five-colour WebGL remap are intentionally kept
// unchanged; this module only makes them deterministic for offline rendering.
const VIDEO_URL = new URL('./Assets/transition.mp4', import.meta.url);

export const UMENG_TRANSITION_DURATION = 3;

const SOURCE_PALETTE = ['#cca4fc', '#ecd4fc', '#4cecec', '#fcec6c', '#ffffff'];
const VERTEX_SHADER = `
    attribute vec2 aPos;
    attribute vec2 aUV;
    varying vec2 vUV;
    void main(){ gl_Position=vec4(aPos,0.0,1.0); vUV=aUV; }
`;
const FRAGMENT_SHADER = `
    precision mediump float;
    uniform sampler2D uTex;
    uniform vec3 uSrc[5];
    uniform vec3 uDst[5];
    varying vec2 vUV;

    float influence(vec3 c, vec3 s, float inner, float outer) {
      float d = distance(c, s);
      return 1.0 - smoothstep(inner, outer, d);
    }

    void main(){
      vec4 px = texture2D(uTex, vUV);
      vec3 c = px.rgb;
      float best = 0.0;
      vec3 replacement = c;
      for (int i=0; i<5; i++) {
        float inner = (i==0) ? 0.025 : 0.018;
        float outer = (i==0) ? 0.155 : ((i==4) ? 0.10 : 0.13);
        float w = influence(c, uSrc[i], inner, outer);
        if (w > best) { best = w; replacement = uDst[i]; }
      }
      float srcLum = dot(c, vec3(0.2126,0.7152,0.0722));
      float dstLum = max(dot(replacement, vec3(0.2126,0.7152,0.0722)), 0.01);
      vec3 shaded = clamp(replacement * mix(1.0, srcLum/dstLum, 0.20), 0.0, 1.0);
      // The source is composited over black. Recover both its alpha and its
      // straight foreground colour; changing alpha alone leaves a dark fringe
      // because antialiased edge pixels still contain the black matte RGB.
      float matte = max(max(c.r, c.g), c.b);
      float alpha = smoothstep(0.45, 0.75, matte);
      vec3 remapped = mix(c, shaded, best);
      vec3 foreground = (alpha > 0.0001)
        ? clamp(remapped / max(matte, 0.0001), 0.0, 1.0)
        : vec3(0.0);
      gl_FragColor = vec4(foreground, alpha);
    }
`;

function compileShader(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
        throw new Error(gl.getShaderInfoLog(shader));
    }
    return shader;
}

function hex(value) {
    const raw = value.replace('#', '');
    return [
        parseInt(raw.slice(0, 2), 16) / 255,
        parseInt(raw.slice(2, 4), 16) / 255,
        parseInt(raw.slice(4, 6), 16) / 255,
    ];
}

function waitFor(video, event, message) {
    return new Promise((resolve, reject) => {
        const onReady = () => {
            video.removeEventListener('error', onError);
            resolve();
        };
        const onError = () => {
            video.removeEventListener(event, onReady);
            reject(new Error(message));
        };
        video.addEventListener(event, onReady, { once: true });
        video.addEventListener('error', onError, { once: true });
    });
}

async function seek(video, time) {
    const target = Math.min(Math.max(0, time), Math.max(0, video.duration - 1 / 120));
    if (Math.abs(video.currentTime - target) < 0.0001 && video.readyState >= 2) return;
    const ready = waitFor(video, 'seeked', '乌蒙转场视频定位失败');
    video.currentTime = target;
    await ready;
}

async function createSurface(size) {
    const video = document.createElement('video');
    video.src = VIDEO_URL.href;
    video.muted = true;
    video.playsInline = true;
    video.preload = 'auto';
    if (video.readyState < 2) await waitFor(video, 'loadeddata', '乌蒙转场视频解码失败');
    video.pause();

    const canvas = document.createElement('canvas');
    canvas.width = size;
    canvas.height = size;
    const gl = canvas.getContext('webgl', {
        alpha: true,
        antialias: false,
        preserveDrawingBuffer: true,
    });
    if (!gl) throw new Error('浏览器不支持乌蒙转场所需的 WebGL');

    const program = gl.createProgram();
    gl.attachShader(program, compileShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER));
    gl.attachShader(program, compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error(gl.getProgramInfoLog(program));
    }
    gl.useProgram(program);

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
        -1, -1, 0, 1, 1, -1, 1, 1, -1, 1, 0, 0,
        -1, 1, 0, 0, 1, -1, 1, 1, 1, 1, 1, 0,
    ]), gl.STATIC_DRAW);
    const position = gl.getAttribLocation(program, 'aPos');
    const uv = gl.getAttribLocation(program, 'aUV');
    gl.enableVertexAttribArray(position);
    gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(uv);
    gl.vertexAttribPointer(uv, 2, gl.FLOAT, false, 16, 8);

    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.uniform1i(gl.getUniformLocation(program, 'uTex'), 0);
    SOURCE_PALETTE.forEach((colour, index) => {
        gl.uniform3fv(gl.getUniformLocation(program, `uSrc[${index}]`), hex(colour));
        gl.uniform3fv(gl.getUniformLocation(program, `uDst[${index}]`), hex(colour));
    });
    gl.viewport(0, 0, size, size);
    return { video, canvas, gl, texture };
}

export async function loadUmengTransitionFrames(fps, size) {
    const surface = await createSurface(size);
    const frames = [];
    const frameCount = Math.ceil(UMENG_TRANSITION_DURATION * fps);
    let completed = false;
    try {
        for (let index = 0; index < frameCount; index++) {
            await seek(surface.video, index / fps);
            surface.gl.activeTexture(surface.gl.TEXTURE0);
            surface.gl.bindTexture(surface.gl.TEXTURE_2D, surface.texture);
            surface.gl.texImage2D(
                surface.gl.TEXTURE_2D,
                0,
                surface.gl.RGBA,
                surface.gl.RGBA,
                surface.gl.UNSIGNED_BYTE,
                surface.video,
            );
            surface.gl.drawArrays(surface.gl.TRIANGLES, 0, 6);
            surface.gl.finish();
            frames.push(await createImageBitmap(surface.canvas));
        }
        completed = true;
        return frames;
    } finally {
        if (!completed) frames.forEach((frame) => frame.close());
        surface.video.removeAttribute('src');
        surface.video.load();
    }
}
