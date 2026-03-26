import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Downward_chevron from './icons/Downward_chevron.tsx'


    
// Component

        function NavigationDropdownTrigger({
            label
        }: {
            label: string;
        }) {
            return (
                <button className={"globalNavigation_link__ofzIw globalNavigation_dropdownTrigger__Vd0Te"}>
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
                    <span className={"globalNavigation_chevron__FLxoW"}>
                        <Downward_chevron />
                    </span>
                </button>
            );
        }
    

export default NavigationDropdownTrigger
