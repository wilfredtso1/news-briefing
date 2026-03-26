import React from 'react'
import type { JSX } from 'react/jsx-runtime'



    
// Component

        function NavigationLink({
            label
        }: {
            label: string;
        }) {
            return (
                <a className={"globalNavigation_link__ofzIw"}>
                    <span
                        className={"typography_typography__Exx2D"}
                        style={{
                            "--typography-font": "var(--typography-sans-100-medium-font)",
                            "--typography-font-sm": "var(--typography-sans-100-medium-font)",
                            "--typography-letter-spacing": "var(--typography-sans-100-medium-letter-spacing)",
                            "--typography-letter-spacing-sm": "var(--typography-sans-100-medium-letter-spacing)",
                            "--typography-color": "inherit"
                        } as React.CSSProperties}
                    >
                        {label}
                    </span>
                </a>
            );
        }
    

export default NavigationLink
