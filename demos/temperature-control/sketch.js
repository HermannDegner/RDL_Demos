let particles = [];
let currentTemp = 20;

class Particle {
    constructor(x, y, temp) {
        this.x = x;
        this.y = y;
        this.vx = random(-2, 2);
        this.vy = random(-2, 2);
        this.life = 255;
        this.temp = temp;
    }

    update() {
        this.x += this.vx;
        this.y += this.vy;
        this.vy += 0.1; // 重力
        this.life -= 3;
    }

    display(canvasWidth, canvasHeight) {
        push();

        // 温度に応じた色を設定
        // 0°C: 青、25°C: 緑、50°C: 赤
        let r, g, b;
        if (this.temp < 25) {
            // 青から緑へ
            const ratio = this.temp / 25;
            r = 50 + 50 * ratio;
            g = 100 + 155 * ratio;
            b = 255 - 155 * ratio;
        } else {
            // 緑から赤へ
            const ratio = (this.temp - 25) / 25;
            r = 100 + 155 * ratio;
            g = 255 - 155 * ratio;
            b = 100 - 100 * ratio;
        }

        // 温度に応じたサイズ
        const size = 3 + (this.temp / 50) * 5;

        // パーティクルを描画
        fill(r, g, b, this.life);
        noStroke();
        ellipse(this.x, this.y, size, size);

        pop();
    }

    isAlive() {
        return this.life > 0;
    }
}

function setup() {
    const container = document.getElementById('sketch-container');
    const width = Math.min(container.clientWidth - 40, 800);
    const height = Math.min(window.innerHeight * 0.6, 600);

    const canvas = createCanvas(width, height);
    canvas.parent('sketch-container');

    // スライダーのイベントリスナーを設定
    const slider = document.getElementById('tempSlider');
    const tempValue = document.getElementById('tempValue');

    slider.addEventListener('input', (e) => {
        currentTemp = parseInt(e.target.value);
        tempValue.textContent = currentTemp;
    });
}

function draw() {
    background(240, 248, 255); // アリスブルー

    // 新しいパーティクルを生成
    for (let i = 0; i < 3; i++) {
        particles.push(
            new Particle(
                random(width),
                random(height * 0.7),
                currentTemp
            )
        );
    }

    // パーティクルを更新して描画
    for (let i = particles.length - 1; i >= 0; i--) {
        particles[i].update();
        particles[i].display(width, height);

        if (!particles[i].isAlive()) {
            particles.splice(i, 1);
        }
    }

    // 温度インジケーターを描画
    push();
    fill(0);
    textSize(16);
    text(`パーティクル数: ${particles.length}`, 10, 30);
    pop();

    // グラデーション背景を表現（温度に応じて）
    let bgColor;
    if (currentTemp < 25) {
        const ratio = currentTemp / 25;
        bgColor = `rgb(${100 + 50 * ratio}, ${150 + 100 * ratio}, ${255 - 100 * ratio})`;
    } else {
        const ratio = (currentTemp - 25) / 25;
        bgColor = `rgb(${150 + 100 * ratio}, ${250 - 150 * ratio}, ${155 - 100 * ratio})`;
    }
}

function windowResized() {
    const container = document.getElementById('sketch-container');
    if (container) {
        const width = Math.min(container.clientWidth - 40, 800);
        const height = Math.min(window.innerHeight * 0.6, 600);
        resizeCanvas(width, height);
    }
}
