import type { JSX } from 'react/jsx-runtime'

import Downward_chevron from './components/icons/Downward_chevron.tsx'

import React from 'react';

export const Downward_chevron_arrow = () => {
    return (
<svg className={"navCaret"} viewBox={"0 0 8 6"} style={{width:"8px", height:"100%", display:"block", fill:"var(--color-icon)", flexShrink:"0"}}>
<path d={"m1 1 3 3 3-3"} stroke={"currentColor"} strokeWidth={"1.5"} fill={"none"}></path>
</svg>    );
}



export default Downward_chevron_arrow
