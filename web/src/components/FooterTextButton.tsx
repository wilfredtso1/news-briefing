import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Footer from './Footer.tsx'


    
// Component

        function FooterTextButton({
            label,
            buttonClass
        }: {
            label: string;
            buttonClass: string;
        }) {
            return (
                <button className={buttonClass} type={"button"}>
                    <span
                        className={"typography_typography__Exx2D"}
                        style={{
                            "--typography-font": "var(--typography-sans-100-regular-font)",
                            "--typography-font-sm": "var(--typography-sans-100-regular-font)",
                            "--typography-letter-spacing": "var(--typography-sans-100-regular-letter-spacing)",
                            "--typography-letter-spacing-sm": "var(--typography-sans-100-regular-letter-spacing)",
                            "--typography-color": "inherit"
                        } as React.CSSProperties}
                    >
                        {label}
                    </span>
                </button>
            );
        }
    

export default FooterTextButton
