const canvas = document.getElementById("c");
const ctx = canvas.getContext("2d");

canvas.width = innerWidth;
canvas.height = innerHeight;

function extractOutline(img) {
    let temp = document.createElement("canvas");
    let tctx = temp.getContext("2d");

    temp.width = img.width;
    temp.height = img.height;

    tctx.drawImage(img, 0, 0);

    let data = tctx.getImageData(0, 0, temp.width, temp.height);
    let px = data.data;

    let points = [];

    for (let y = 1; y < temp.height - 1; y++) {
        for (let x = 1; x < temp.width - 1; x++) {

            let i = (y * temp.width + x) * 4;

            let b = px[i] < 128 ? 1 : 0;
            let left = px[(y * temp.width + (x - 1)) * 4] < 128 ? 1 : 0;
            let right = px[(y * temp.width + (x + 1)) * 4] < 128 ? 1 : 0;
            let up = px[((y - 1) * temp.width + x) * 4] < 128 ? 1 : 0;
            let down = px[((y + 1) * temp.width + x) * 4] < 128 ? 1 : 0;

            if (b === 1 && (left + right + up + down) < 4) {
                points.push({ x, y });
            }
        }
    }

    return points;
}

function DFT(points) {
    const N = points.length;
    let X = [];

    for (let k = 0; k < N; k++) {
        let re = 0, im = 0;

        for (let n = 0; n < N; n++) {
            let phi = (2 * Math.PI * k * n) / N;
            re += points[n].x * Math.cos(phi) + points[n].y * Math.sin(phi);
            im += -points[n].x * Math.sin(phi) + points[n].y * Math.cos(phi);
        }

        re /= N;
        im /= N;

        X.push({
            freq: k,
            amp: Math.sqrt(re * re + im * im),
            phase: Math.atan2(im, re)
        });
    }

    return X.sort((a, b) => b.amp - a.amp);
}

let fourier = null;
let path = [];
let time = 0;

function epicycles(cx, cy, f) {
    for (let v of f) {
        let px = cx;
        let py = cy;

        cx += v.amp * Math.cos(time * v.freq + v.phase);
        cy += v.amp * Math.sin(time * v.freq + v.phase);

        ctx.strokeStyle = "rgba(255,255,255,0.15)";
        ctx.beginPath();
        ctx.arc(px, py, v.amp, 0, Math.PI * 2);
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(cx, cy);
        ctx.stroke();
    }

    return { x: cx, y: cy };
}

function animate() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (fourier) {
        let v = epicycles(canvas.width / 2, canvas.height / 2, fourier);

        path.unshift(v);

        ctx.strokeStyle = "cyan";
        ctx.beginPath();
        for (let i = 1; i < path.length; i++) {
            ctx.moveTo(path[i].x, path[i].y);
            ctx.lineTo(path[i - 1].x, path[i - 1].y);
        }
        ctx.stroke();

        time += (2 * Math.PI) / fourier.length;
        if (time > 2 * Math.PI) {
            time = 0;
            path = [];
        }
    }

    requestAnimationFrame(animate);
}

animate();

document.getElementById("imgFile").onchange = function (e) {
    let img = new Image();
    img.onload = () => {
        let points = extractOutline(img);

        console.log("Extracted pts:", points.length);

        if (points.length === 0) {
            alert("NO EDGES FOUND! Use a dark outline image.");
            return;
        }

        let cx = img.width / 2;
        let cy = img.height / 2;

        points = points.map(p => ({
            x: p.x - cx,
            y: p.y - cy
        }));

        fourier = DFT(points);
        path = [];
        time = 0;
    };
    img.src = URL.createObjectURL(e.target.files[0]);
};
