#version 330
in vec2 v_uv;
out vec4 fragColor;

uniform vec2 u_resolution;
uniform vec2 u_gaze;
uniform float u_time;
uniform float u_happiness;
uniform float u_energy;
uniform float u_stress;
uniform float u_curiosity;
uniform float u_rate;
uniform float u_dopamine;
uniform float u_open;
uniform int u_emotion;
uniform int u_particle_count;
uniform vec4 u_particles[48];

float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float noise21(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x),
               mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 4; ++i) {
        v += a * noise21(p);
        p = mat2(1.61, 1.17, -1.17, 1.61) * p + 13.7;
        a *= 0.5;
    }
    return v;
}

float segmentDistance(vec2 p, vec2 a, vec2 b) {
    vec2 pa = p - a, ba = b - a;
    float h = clamp(dot(pa, ba) / max(dot(ba, ba), 0.00001), 0.0, 1.0);
    return length(pa - ba * h);
}

float circleMask(float d, float width) {
    return 1.0 - smoothstep(width * 0.35, width, d);
}

float bezierLid(float t, float controlHeight) {
    float u = 1.0 - t;
    return 3.0 * u * u * t * controlHeight
         + 3.0 * u * t * t * controlHeight;
}

void main() {
    vec2 uv = v_uv;
    vec2 p = (uv - 0.5) * 2.0;
    float aspect = u_resolution.x / u_resolution.y;
    p.x *= aspect;
    float t = u_time;

    vec3 bg = vec3(0.012, 0.025, 0.035);
    float grid = step(0.985, fract(uv.x * 28.0)) + step(0.988, fract(uv.y * 18.0));
    bg += vec3(0.006, 0.022, 0.028) * min(grid, 1.0);
    float star = step(0.9978, hash21(floor(uv * vec2(94.0, 54.0))));
    bg += star * vec3(0.02, 0.22, 0.27) * (0.4 + 0.6 * sin(t * 2.0 + uv.x * 9.0));

    float normalizedX = abs(p.x) / (aspect * 0.94);
    float arc = pow(max(0.0, 1.0 - normalizedX * normalizedX), 0.68);
    float opening = clamp(u_open, 0.20, 1.08);
    if (u_emotion == 2) opening += 0.018 * sin(t * 25.0);

    float blink = 0.0;
    float phase = mod(t, u_emotion == 3 ? 5.4 : 4.1);
    blink = max(blink, max(0.0, 1.0 - abs(phase - 0.10) / 0.105));
    if (u_emotion == 1 || u_emotion == 6) {
        blink = max(blink, max(0.0, 1.0 - abs(phase - 0.30) / 0.095));
    }
    if (u_emotion == 6) blink = max(blink, 0.92 * abs(sin(t * 2.8)));
    opening *= 1.0 - blink * 0.96;

    float lidT = 0.5 + 0.5 * clamp(normalizedX, 0.0, 1.0);
    float upperBezier = bezierLid(lidT, opening * 1.333);
    float lowerBezier = bezierLid(lidT, opening * 1.12);
    float upperEdge = upperBezier - 0.035 * p.x / aspect;
    float lowerEdge = -lowerBezier - 0.018 * p.x / aspect;
    float eyeD = max(p.y - upperEdge, lowerEdge - p.y);
    float eye = 1.0 - smoothstep(-0.012, 0.015, eyeD);
    float socketOpen = 1.20;
    float socketD = max(p.y - arc * socketOpen, -arc * socketOpen * 0.88 - p.y);
    float socket = 1.0 - smoothstep(-0.035, 0.025, socketD);

    vec3 color = mix(bg, vec3(0.035, 0.11, 0.14), socket);
    float socketRim = 1.0 - smoothstep(0.008, 0.027, abs(socketD));
    color += socketRim * vec3(0.03, 0.23, 0.27) * socket;

    vec2 irisCenter = vec2((u_gaze.x * 0.11 + sin(t * 6.0) * u_rate * 0.003) * aspect,
                           -u_gaze.y * 0.07 + cos(t * 4.0) * u_dopamine * 0.006);
    vec2 irisP = p - irisCenter;
    float irisR = length(irisP);
    float angle = mod(atan(irisP.y, irisP.x) + 6.2831853, 6.2831853);

    vec3 sclera = mix(vec3(0.59, 0.72, 0.71), vec3(0.87, 0.91, 0.86),
                      clamp(0.55 + p.y * 0.42, 0.0, 1.0));
    sclera *= 0.90 + 0.10 * fbm(p * 26.0 + vec2(0.0, t * 0.02));
    sclera *= 0.84 + 0.16 * (1.0 - smoothstep(0.1, 0.94, abs(p.x) / aspect));

    float veins = 0.0;
    for (int i = 0; i < 12; ++i) {
        float a = 6.2831853 * (float(i) / 12.0) + 0.13 * sin(float(i) * 3.0);
        vec2 dir = vec2(cos(a), sin(a));
        float along = dot(irisP, dir);
        float across = abs(dot(irisP, vec2(-dir.y, dir.x))
                         - 0.012 * sin(along * 19.0 + float(i)));
        float vein = (1.0 - smoothstep(0.0015, 0.006, across))
                   * smoothstep(0.43, 0.51, along)
                   * (1.0 - smoothstep(0.76, 0.90, along));
        veins = max(veins, vein);
    }
    sclera = mix(sclera, vec3(0.54, 0.40, 0.39), veins * 0.22);
    color = mix(color, sclera, eye);

    float irisMask = 1.0 - smoothstep(0.418, 0.438, irisR);
    float fiberNoise = fbm(vec2(angle * 3.4, irisR * 17.0));
    float fibers = 0.5 + 0.5 * sin(angle * 92.0 + fiberNoise * 5.0
                                    + irisR * 112.0 + 0.8 * sin(angle * 19.0));
    float fineFiber = 0.5 + 0.5 * sin(angle * 177.0 + irisR * 51.0 + fiberNoise * 9.0);
    vec3 cyan = vec3(0.06, 0.53, 0.58);
    vec3 amber = vec3(0.78, 0.43, 0.10);
    vec3 irisBase = mix(amber, cyan, clamp(u_happiness * 0.72 + u_curiosity * 0.20, 0.0, 1.0));
    float fiberLight = 0.42 + fibers * 0.33 + fineFiber * 0.12 + fiberNoise * 0.18;
    float innerGlow = 1.0 - smoothstep(0.17, 0.34, irisR);
    vec3 iris = irisBase * fiberLight + vec3(0.13, 0.08, 0.025) * innerGlow;
    iris *= 0.78 + 0.22 * (1.0 - smoothstep(0.12, 0.43, irisR));
    float limbus = 1.0 - smoothstep(0.006, 0.025, abs(irisR - 0.421));
    iris = mix(iris, vec3(0.008, 0.055, 0.075), limbus * 0.92);
    float collarette = 1.0 - smoothstep(0.006, 0.018, abs(irisR - 0.245));
    iris += collarette * vec3(0.20, 0.15, 0.065);

    for (int i = 0; i < 72; ++i) {
        float a = 6.2831853 * (float(i) / 72.0);
        float radial = abs(angle - a);
        radial = min(radial, 6.2831853 - radial);
        float fiber = (1.0 - smoothstep(0.009, 0.030, radial))
                    * smoothstep(0.25, 0.34, irisR)
                    * (1.0 - smoothstep(0.38, 0.415, irisR));
        iris += fiber * (i % 6 == 0 ? vec3(0.16, 0.12, 0.04) : vec3(0.025, 0.10, 0.13));
    }

    float pupilRadius = 0.105 + 0.095 * clamp(u_stress, 0.0, 1.0)
                      + 0.018 * (1.0 - clamp(u_energy, 0.0, 1.0));
    float pupil = 1.0 - smoothstep(pupilRadius - 0.008, pupilRadius + 0.008, irisR);
    color = mix(color, iris, irisMask * eye);
    color = mix(color, vec3(0.006, 0.012, 0.017), pupil * eye);

    float tickRing = 1.0 - smoothstep(0.004, 0.012, abs(irisR - 0.365));
    float ticks = step(0.86, fract(angle * 16.0 / 6.2831853));
    color += tickRing * ticks * vec3(0.35, 0.23, 0.06) * eye;

    vec2 glint1 = irisCenter + vec2(-0.11, 0.16);
    vec2 glint2 = irisCenter + vec2(0.14, -0.10);
    float reflection1 = circleMask(length(irisP - glint1) - 0.025, 0.025);
    float reflection2 = circleMask(length(irisP - glint2) - 0.010, 0.010);
    float reflectionHalo = exp(-length(irisP - glint1) * 24.0) * 0.30;
    color += (reflection1 * 0.9 + reflection2 * 0.75 + reflectionHalo)
           * vec3(0.70, 0.96, 1.0) * eye;

    float upperShadow = exp(-max(0.0, upperEdge - p.y) * 15.0)
                      * smoothstep(-0.85, 0.85, p.y) * eye;
    color *= 1.0 - upperShadow * 0.35;
    float upperLid = 1.0 - smoothstep(0.008, 0.020, abs(p.y - upperEdge));
    float lowerLid = 1.0 - smoothstep(0.008, 0.022, abs(p.y - lowerEdge));
    vec3 lidColor = u_emotion == 2 ? vec3(0.88, 0.30, 0.20)
                  : u_emotion == 3 ? vec3(0.26, 0.66, 0.78)
                  : vec3(0.12, 0.75, 0.81);
    color = mix(color, lidColor, upperLid * 0.90);
    color = mix(color, lidColor * 0.55, lowerLid * 0.75);

    float lashes = 0.0;
    for (int i = 0; i < 25; ++i) {
        float s = float(i) / 24.0;
        float x = (s * 1.62 - 0.81) * aspect;
        float nx = abs(x) / (aspect * 0.94);
        float y = bezierLid(0.5 + 0.5 * nx, opening * 1.333)
                - 0.035 * x / aspect;
        float len = (0.045 + 0.045 * (1.0 - abs(s - 0.5) * 2.0))
                  * (u_emotion == 2 ? 0.72 : 1.0);
        vec2 a = vec2(x, y);
        vec2 b = a + vec2((s - 0.5) * 0.12, len);
        lashes = max(lashes, 1.0 - smoothstep(0.004, 0.012, segmentDistance(p, a, b)));
    }
    color = mix(color, vec3(0.045, 0.12, 0.15), lashes * eye);

    if (u_emotion == 3) {
        float tearPhase = fract(t * 0.32);
        vec2 tearP = p - vec2(0.39 * aspect, 0.12 - tearPhase * 0.42);
        float tear = circleMask(length(tearP * vec2(1.0, 0.72)) - 0.035, 0.035);
        float tearGlow = exp(-length(tearP) * 16.0) * 0.32;
        color = mix(color, vec3(0.21, 0.82, 0.95), tear * 0.88 + tearGlow);
    }

    if (u_emotion == 1) {
        for (int i = 0; i < 8; ++i) {
            float a = 6.2831853 * float(i) / 8.0 + t * 0.18;
            vec2 starP = p - vec2(cos(a) * 0.70 * aspect, sin(a) * 0.56);
            float starD = min(abs(starP.x), abs(starP.y));
            float sparkle = (1.0 - smoothstep(0.008, 0.022, starD))
                          * (1.0 - smoothstep(0.020, 0.10, length(starP)));
            color += sparkle * vec3(0.55, 0.34, 0.08) * (0.55 + 0.45 * sin(t * 6.0 + float(i)));
        }
    }

    for (int i = 0; i < 48; ++i) {
        if (i >= u_particle_count) break;
        vec4 particle = u_particles[i];
        vec2 particleP = (uv - particle.xy) * vec2(aspect, 1.0);
        float radius = particle.z * (0.82 + 0.18 * sin(t * 5.0 + float(i)));
        float glow = exp(-length(particleP) / max(radius * 6.0, 0.001)) * particle.w;
        float core = circleMask(length(particleP) - radius, radius);
        color += vec3(0.05, 0.65, 0.78) * glow + vec3(0.55, 0.90, 1.0) * core;
    }

    float scan = 0.97 + 0.03 * sin(uv.y * u_resolution.y * 1.2);
    float vignette = 1.0 - 0.34 * smoothstep(0.25, 1.05, length((uv - 0.5) * vec2(1.0, 0.82)));
    float bloom = max(reflection1, reflection2) * 0.13;
    color = color * scan * vignette + bloom * vec3(0.25, 0.48, 0.54);
    fragColor = vec4(color, 1.0);
}
