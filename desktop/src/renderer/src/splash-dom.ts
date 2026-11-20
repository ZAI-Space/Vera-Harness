/**
 * 开屏 DOM 生成：index.html 中排在主 bundle 前的独立 module，首帧前同步建 DOM
 * （样式 splash.css 渲染阻塞先行就绪，本文件只一次性建 DOM；就绪收场由 splash-orbits.ts 接管）。
 * 三圈小球的大小与间距在 splash-orbits.ts 中定义，配色与双环散场在 splash.css 中统一。
 */

import veraLogo from "./assets/splash/vera-logo.png";
import { buildSplashOrbits } from "./splash-orbits";

const splash = document.createElement("div");
splash.id = "splash";
splash.innerHTML = `
	<div class="sp-swarm" aria-hidden="true">
		<div class="sp-swarm-in">
			${buildSplashOrbits()}
		</div>
	</div>
	<div class="sp-wave" aria-hidden="true"></div>
	<div class="sp-wave sp-wave-echo" aria-hidden="true"></div>
	<img class="sp-word" src="${veraLogo}" width="468" height="220" alt="VERA" draggable="false" />
	<div class="sp-line" role="progressbar"></div>
	<div class="sp-status text-ui-12" role="status"></div>`;
document.body.append(splash);
