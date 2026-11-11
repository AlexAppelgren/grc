'use client';

import { useEffect, useRef } from 'react';

// The public page's logo (design/public/index.html, the Lexicon direction, Alex
// 2026-11-11): the phonetic name cut out of the green page, with ink moving in
// water behind the letters. A small fluid simulation on WebGL2 half-float
// targets carries the ink, so the pointer drags it in every direction and
// leaves a wake, and the ink settles back into its resting pattern in a few
// seconds. The reference's script is the specification; the shaders below are
// its own, and their colours are the paper, the green and a blue ink.
//
// Three fallbacks, named on the element as data-ink for the tests:
//   fluid    the simulation
//   pattern  the resting pattern, animated, when the simulation cannot start
//   still    one frame of it under prefers-reduced-motion
//   css      the element's own background, when there is no WebGL at all
// The loop stops while the logo is off screen.

const VS =
  'attribute vec2 a;varying vec2 vUv,vL,vR,vT,vB;uniform vec2 texel;void main(){vUv=a*.5+.5;vL=vUv-vec2(texel.x,0.);vR=vUv+vec2(texel.x,0.);vT=vUv+vec2(0.,texel.y);vB=vUv-vec2(0.,texel.y);gl_Position=vec4(a,0.,1.);}';
const HEAD = 'precision highp float;varying vec2 vUv,vL,vR,vT,vB;';
const INK = [
  'float h(vec2 p){p=fract(p*vec2(123.34,456.21));p+=dot(p,p+45.32);return fract(p.x*p.y);}',
  'float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}',
  'float fbm(vec2 p){float v=0.,a=.5;mat2 m=mat2(.8,-.6,.6,.8);for(int i=0;i<5;i++){v+=a*n(p);p=m*p*2.03+11.7;a*=.5;}return v;}',
  // Where the ink rests: x is the amount of ink, y the share of blue ink, z a value for thin light edges.
  'vec3 pattern(vec2 uv,float T){vec2 p=uv*1.15;float t=T*.035;',
  ' vec2 q=vec2(fbm(p+vec2(0.,t)),fbm(p+vec2(5.2,-t*1.3)));',
  ' vec2 r=vec2(fbm(p+3.6*q+vec2(1.7,9.2)+t*.8),fbm(p+3.6*q+vec2(8.3,2.8)-t*.6));',
  ' float f=fbm(p+3.4*r);',
  ' return vec3(smoothstep(.485,.77,f*.75+.42*r.x+.08*sin(uv.x*1.3+t*3.)),smoothstep(.58,.8,q.y),f);}',
  'vec3 shade(vec3 d,vec2 px,float T){float ink=clamp(d.x,0.,1.);',
  ' vec3 water=vec3(.965,.953,.925),green=vec3(.05,.45,.30),deep=vec3(.02,.17,.115),blue=vec3(.16,.18,.52);',
  ' vec3 c=mix(water,green,smoothstep(0.,.55,ink));c=mix(c,deep,smoothstep(.62,1.,ink)*.85);',
  ' c=mix(c,blue,clamp(d.y,0.,1.)*smoothstep(.15,.6,ink)*.4);',
  ' float edge=1.-smoothstep(0.,.035,abs(d.z-.5));c=mix(c,water,edge*.18*(1.-ink));',
  ' return c+(h(px+T)-.5)*.035;}',
].join('\n');

type GL = WebGLRenderingContext | WebGL2RenderingContext;
type Program = { bind: () => void; loc: (name: string) => WebGLUniformLocation | null };
type Target = { tex: WebGLTexture; fb: WebGLFramebuffer; w: number; h: number };
type Pair = { read: Target; write: Target; swap: () => void };
type Splat = { x: number; y: number; vx: number; vy: number; ink: number };
type InkMode = 'fluid' | 'pattern' | 'still' | 'css';

/** Starts the ink in the canvas and returns the mode it runs in and how to stop it. */
function startInk(head: HTMLElement, cv: HTMLCanvasElement): { mode: InkMode; stop: () => void } {
  const undo: (() => void)[] = [];
  const stop = () => undo.forEach((fn) => fn());
  const opts: WebGLContextAttributes = { antialias: false, alpha: false, powerPreference: 'low-power' };
  const gl2 = cv.getContext('webgl2', opts);
  const found: GL | null = gl2 ?? cv.getContext('webgl', opts);
  if (found === null) return { mode: 'css', stop };
  const gl: GL = found;

  function compile(type: number, src: string): WebGLShader | null {
    const shader = gl.createShader(type);
    if (shader === null) return null;
    gl.shaderSource(shader, src);
    gl.compileShader(shader);
    return shader;
  }
  function program(fs: string): Program | null {
    const p = gl.createProgram();
    const vs = compile(gl.VERTEX_SHADER, VS);
    const frag = compile(gl.FRAGMENT_SHADER, HEAD + fs);
    if (p === null || vs === null || frag === null) return null;
    gl.attachShader(p, vs);
    gl.attachShader(p, frag);
    gl.bindAttribLocation(p, 0, 'a');
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) return null;
    const uniforms = new Map<string, WebGLUniformLocation | null>();
    return {
      bind: () => gl.useProgram(p),
      loc: (name) => {
        if (!uniforms.has(name)) uniforms.set(name, gl.getUniformLocation(p, name));
        return uniforms.get(name) ?? null;
      },
    };
  }

  // One triangle that covers the whole viewport.
  gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);
  gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

  function size() {
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    const w = Math.max(2, Math.round(cv.clientWidth * dpr));
    const h = Math.max(2, Math.round(cv.clientHeight * dpr));
    if (cv.width !== w || cv.height !== h) {
      cv.width = w;
      cv.height = h;
    }
  }

  // The loop runs only while the logo is on screen, and starts again when it returns.
  let visible = true;
  let frame = 0;
  let step: ((now: number) => void) | null = null;
  const schedule = () => {
    if (frame === 0 && visible && step !== null) frame = requestAnimationFrame(tick);
  };
  function tick(now: number) {
    frame = 0;
    step?.(now);
    schedule();
  }
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      visible = entries.some((entry) => entry.isIntersecting);
      schedule();
    });
    observer.observe(head);
    undo.push(() => observer.disconnect());
  }
  undo.push(() => {
    step = null;
    cancelAnimationFrame(frame);
  });
  const loop = (fn: (now: number) => void) => {
    step = fn;
    schedule();
  };
  const t0 = performance.now();

  // The resting pattern alone: animated when the simulation cannot start, one frame under reduced motion.
  function still(animate: boolean): boolean {
    const P = program(`${INK}\nuniform vec2 R;uniform float T;void main(){vec2 uv=gl_FragCoord.xy/R.y;gl_FragColor=vec4(shade(pattern(uv,T),gl_FragCoord.xy,T),1.);}`);
    if (P === null) return false;
    const draw = (now: number) => {
      size();
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, cv.width, cv.height);
      P.bind();
      gl.uniform2f(P.loc('R'), cv.width, cv.height);
      gl.uniform1f(P.loc('T'), animate ? 40 + (now - t0) / 1000 : 40);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    };
    if (animate) {
      loop(draw);
    } else {
      const redraw = () => draw(t0);
      redraw();
      window.addEventListener('resize', redraw);
      undo.push(() => window.removeEventListener('resize', redraw));
    }
    return true;
  }

  function fluid(): boolean {
    if (gl2 === null || !(gl2.getExtension('EXT_color_buffer_float') || gl2.getExtension('EXT_color_buffer_half_float'))) return false;
    const g = gl2;
    size();
    const aspect = cv.width / cv.height;
    const SH = 112;
    const SW = Math.round(SH * aspect);
    const DH = 288;
    const DW = Math.round(DH * aspect);

    function target(w: number, h: number): Target | null {
      const tex = g.createTexture();
      const fb = g.createFramebuffer();
      if (tex === null || fb === null) return null;
      g.bindTexture(g.TEXTURE_2D, tex);
      g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MIN_FILTER, g.LINEAR);
      g.texParameteri(g.TEXTURE_2D, g.TEXTURE_MAG_FILTER, g.LINEAR);
      g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_S, g.CLAMP_TO_EDGE);
      g.texParameteri(g.TEXTURE_2D, g.TEXTURE_WRAP_T, g.CLAMP_TO_EDGE);
      g.texImage2D(g.TEXTURE_2D, 0, g.RGBA16F, w, h, 0, g.RGBA, g.HALF_FLOAT, null);
      g.bindFramebuffer(g.FRAMEBUFFER, fb);
      g.framebufferTexture2D(g.FRAMEBUFFER, g.COLOR_ATTACHMENT0, g.TEXTURE_2D, tex, 0);
      if (g.checkFramebufferStatus(g.FRAMEBUFFER) !== g.FRAMEBUFFER_COMPLETE) return null;
      g.viewport(0, 0, w, h);
      g.clearColor(0, 0, 0, 1);
      g.clear(g.COLOR_BUFFER_BIT);
      return { tex, fb, w, h };
    }
    function pair(w: number, h: number): Pair | null {
      const a = target(w, h);
      const b = target(w, h);
      if (a === null || b === null) return null;
      const p: Pair = {
        read: a,
        write: b,
        swap: () => {
          [p.read, p.write] = [p.write, p.read];
        },
      };
      return p;
    }
    const vel = pair(SW, SH);
    const dye = pair(DW, DH);
    const prs = pair(SW, SH);
    const div = target(SW, SH);
    const crl = target(SW, SH);
    if (vel === null || dye === null || prs === null || div === null || crl === null) return false;

    const splatP = program('uniform sampler2D uT;uniform float aspect,radius;uniform vec3 color;uniform vec2 point;void main(){vec2 p=vUv-point;p.x*=aspect;gl_FragColor=vec4(texture2D(uT,vUv).xyz+exp(-dot(p,p)/radius)*color,1.);}');
    const advectP = program('uniform sampler2D uV,uS;uniform vec2 vtexel;uniform float dt,diss;void main(){vec2 c=vUv-dt*texture2D(uV,vUv).xy*vtexel;gl_FragColor=vec4(texture2D(uS,c).xyz/(1.+diss*dt),1.);}');
    const divP = program('uniform sampler2D uV;void main(){float L=texture2D(uV,vL).x,R=texture2D(uV,vR).x,T=texture2D(uV,vT).y,B=texture2D(uV,vB).y;vec2 C=texture2D(uV,vUv).xy;if(vL.x<0.){L=-C.x;}if(vR.x>1.){R=-C.x;}if(vT.y>1.){T=-C.y;}if(vB.y<0.){B=-C.y;}gl_FragColor=vec4(.5*(R-L+T-B),0.,0.,1.);}');
    const curlP = program('uniform sampler2D uV;void main(){float L=texture2D(uV,vL).y,R=texture2D(uV,vR).y,T=texture2D(uV,vT).x,B=texture2D(uV,vB).x;gl_FragColor=vec4(.5*(R-L-T+B),0.,0.,1.);}');
    const vortP = program('uniform sampler2D uV,uC;uniform float curl,dt;void main(){float L=texture2D(uC,vL).x,R=texture2D(uC,vR).x,T=texture2D(uC,vT).x,B=texture2D(uC,vB).x,C=texture2D(uC,vUv).x;vec2 f=.5*vec2(abs(T)-abs(B),abs(R)-abs(L));f/=length(f)+.0001;f*=curl*C;f.y*=-1.;gl_FragColor=vec4(clamp(texture2D(uV,vUv).xy+f*dt,-1000.,1000.),0.,1.);}');
    const prsP = program('uniform sampler2D uP,uD;void main(){float L=texture2D(uP,vL).x,R=texture2D(uP,vR).x,T=texture2D(uP,vT).x,B=texture2D(uP,vB).x;gl_FragColor=vec4((L+R+B+T-texture2D(uD,vUv).x)*.25,0.,0.,1.);}');
    const fadeP = program('uniform sampler2D uT;uniform float value;void main(){gl_FragColor=value*texture2D(uT,vUv);}');
    const gradP = program('uniform sampler2D uP,uV;void main(){float L=texture2D(uP,vL).x,R=texture2D(uP,vR).x,T=texture2D(uP,vT).x,B=texture2D(uP,vB).x;gl_FragColor=vec4(texture2D(uV,vUv).xy-vec2(R-L,T-B),0.,1.);}');
    const settleP = program(`${INK}\nuniform sampler2D uT;uniform float aspect,T,k;void main(){gl_FragColor=vec4(mix(texture2D(uT,vUv).xyz,pattern(vUv*vec2(aspect,1.),T),k),1.);}`);
    const showP = program(`${INK}\nuniform sampler2D uT;uniform float T;void main(){gl_FragColor=vec4(shade(texture2D(uT,vUv).xyz,gl_FragCoord.xy,T),1.);}`);
    if (!splatP || !advectP || !divP || !curlP || !vortP || !prsP || !fadeP || !gradP || !settleP || !showP) return false;

    function tex(P: Program, name: string, t: Target, unit: number) {
      g.activeTexture(g.TEXTURE0 + unit);
      g.bindTexture(g.TEXTURE_2D, t.tex);
      g.uniform1i(P.loc(name), unit);
    }
    function draw(P: Program, to: Target | null) {
      if (to === null) {
        g.bindFramebuffer(g.FRAMEBUFFER, null);
        g.viewport(0, 0, cv.width, cv.height);
      } else {
        g.bindFramebuffer(g.FRAMEBUFFER, to.fb);
        g.viewport(0, 0, to.w, to.h);
        g.uniform2f(P.loc('texel'), 1 / to.w, 1 / to.h);
      }
      g.drawArrays(g.TRIANGLES, 0, 3);
    }
    const splat = ({ x, y, vx, vy, ink }: Splat) => {
      splatP.bind();
      g.uniform1f(splatP.loc('aspect'), aspect);
      g.uniform2f(splatP.loc('point'), x, y);
      tex(splatP, 'uT', vel.read, 0);
      g.uniform1f(splatP.loc('radius'), 0.014);
      g.uniform3f(splatP.loc('color'), vx, vy, 0);
      draw(splatP, vel.write);
      vel.swap();
      tex(splatP, 'uT', dye.read, 0);
      g.uniform1f(splatP.loc('radius'), 0.004);
      g.uniform3f(splatP.loc('color'), ink, 0, 0);
      draw(splatP, dye.write);
      dye.swap();
    };
    const settle = (T: number, k: number) => {
      settleP.bind();
      tex(settleP, 'uT', dye.read, 0);
      g.uniform1f(settleP.loc('aspect'), aspect);
      g.uniform1f(settleP.loc('T'), T);
      g.uniform1f(settleP.loc('k'), k);
      draw(settleP, dye.write);
      dye.swap();
    };
    let T = 40;
    settle(T, 1);

    // The water takes most of the pointer's own speed, which is what makes the ink follow it.
    const queue: Splat[] = [];
    let last: { x: number; y: number; t: number } | null = null;
    function point(e: PointerEvent) {
      const b = head.getBoundingClientRect();
      const x = (e.clientX - b.left) / b.width;
      const y = 1 - (e.clientY - b.top) / b.height;
      const now = performance.now();
      if (x < -0.04 || x > 1.04 || y < -0.25 || y > 1.25) {
        last = null;
        return;
      }
      if (last !== null) {
        const dt = Math.max(8, Math.min(50, now - last.t)) / 1000;
        const dx = x - last.x;
        const dy = y - last.y;
        const steps = Math.min(8, Math.max(1, Math.ceil(Math.hypot(dx * aspect, dy) / 0.03)));
        for (let i = 1; i <= steps; i += 1) {
          queue.push({
            x: last.x + (dx * i) / steps,
            y: last.y + (dy * i) / steps,
            vx: ((dx / dt) * SW * 0.7) / steps,
            vy: ((dy / dt) * SH * 0.7) / steps,
            ink: Math.min(0.05, Math.hypot(dx * aspect, dy) * 0.8) / steps,
          });
        }
      }
      last = { x, y, t: now };
    }
    const press = (e: PointerEvent) => {
      last = null;
      point(e);
    };
    const leave = () => {
      last = null;
    };
    window.addEventListener('pointermove', point, { passive: true });
    window.addEventListener('pointerdown', press, { passive: true });
    head.addEventListener('pointerleave', leave);
    undo.push(() => {
      window.removeEventListener('pointermove', point);
      window.removeEventListener('pointerdown', press);
      head.removeEventListener('pointerleave', leave);
    });

    let prev = performance.now();
    loop((now) => {
      const dt = Math.min(0.033, Math.max(0.004, (now - prev) / 1000));
      prev = now;
      T += dt;
      size();
      g.disable(g.BLEND);
      for (let s = queue.shift(); s !== undefined; s = queue.shift()) splat(s);
      curlP.bind();
      tex(curlP, 'uV', vel.read, 0);
      draw(curlP, crl);
      vortP.bind();
      tex(vortP, 'uV', vel.read, 0);
      tex(vortP, 'uC', crl, 1);
      g.uniform1f(vortP.loc('curl'), 14);
      g.uniform1f(vortP.loc('dt'), dt);
      draw(vortP, vel.write);
      vel.swap();
      divP.bind();
      tex(divP, 'uV', vel.read, 0);
      draw(divP, div);
      fadeP.bind();
      tex(fadeP, 'uT', prs.read, 0);
      g.uniform1f(fadeP.loc('value'), 0.8);
      draw(fadeP, prs.write);
      prs.swap();
      prsP.bind();
      tex(prsP, 'uD', div, 1);
      for (let i = 0; i < 16; i += 1) {
        tex(prsP, 'uP', prs.read, 0);
        draw(prsP, prs.write);
        prs.swap();
      }
      gradP.bind();
      tex(gradP, 'uP', prs.read, 0);
      tex(gradP, 'uV', vel.read, 1);
      draw(gradP, vel.write);
      vel.swap();
      advectP.bind();
      g.uniform2f(advectP.loc('vtexel'), 1 / SW, 1 / SH);
      g.uniform1f(advectP.loc('dt'), dt);
      tex(advectP, 'uV', vel.read, 0);
      tex(advectP, 'uS', vel.read, 1);
      g.uniform1f(advectP.loc('diss'), 0.9);
      draw(advectP, vel.write);
      vel.swap();
      tex(advectP, 'uV', vel.read, 0);
      tex(advectP, 'uS', dye.read, 1);
      g.uniform1f(advectP.loc('diss'), 0);
      draw(advectP, dye.write);
      dye.swap();
      settle(T, 1 - Math.exp(-0.34 * dt));
      showP.bind();
      tex(showP, 'uT', dye.read, 0);
      g.uniform1f(showP.loc('T'), T);
      draw(showP, null);
    });
    return true;
  }

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduce) return { mode: still(false) ? 'still' : 'css', stop };
  if (fluid()) return { mode: 'fluid', stop };
  return { mode: still(true) ? 'pattern' : 'css', stop };
}

/** The ink logo: the phonetic name cut out of the page, decorative, since the entry under it names the brand. */
export function InkHead({ phonetic }: { phonetic: string }) {
  const headRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const head = headRef.current;
    const cv = canvasRef.current;
    if (head === null || cv === null) return;
    const { mode, stop } = startInk(head, cv);
    head.dataset.ink = mode;
    // A context that drew nothing would cover the background with black.
    cv.hidden = mode === 'css';
    return stop;
  }, []);

  // The view is cropped to the ink of the two brackets, 61.6 to 938.8 of the line's 1000
  // units in Noto Sans Mono at 700 (measured in the browser, 2026-11-11), and the logo
  // takes the page's own gutter, so the brackets start and end where the bar, the
  // entries and the demo do (Alex, 2026-11-11).
  return (
    <div
      ref={headRef}
      aria-hidden="true"
      data-ink="css"
      className="ink-still relative mx-(--gutter) mt-[clamp(1.5rem,3.5vw,3rem)] aspect-[877.2/262] touch-pan-y"
    >
      <canvas ref={canvasRef} className="absolute inset-0 block size-full" />
      {/* The green reaches a few units past the view on every side, so no edge of the canvas shows as a seam. */}
      <svg viewBox="61.6 0 877.2 262" preserveAspectRatio="none" className="absolute inset-0 block size-full overflow-visible">
        <defs>
          {/* A mask's white keeps the page and its black cuts the letters out: luminance, not colours on screen. */}
          <mask id="ink-cut" maskUnits="userSpaceOnUse" x="57.6" y="-4" width="885.2" height="270">
            <rect x="57.6" y="-4" width="885.2" height="270" fill="#fff" />
            <text x="500" y="207" textAnchor="middle" fontSize="236" textLength="984" lengthAdjust="spacingAndGlyphs" fill="#000" className="font-mono font-bold">
              {phonetic}
            </text>
          </mask>
        </defs>
        <rect x="57.6" y="-4" width="885.2" height="270" mask="url(#ink-cut)" className="fill-brand" />
      </svg>
    </div>
  );
}
