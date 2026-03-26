import React from 'react'
import type { JSX } from 'react/jsx-runtime'



// Component

        function PrimaryLinkButton({
            label
        }: {
            label: string;
        }) {
            return (
                <a className={"button_button__atjat button_buttonVariantPrimary__mUFQZ button_buttonSizeM__NexGD"}>
                    <span
                        className={"typography_typography__Exx2D globalNavigation_noWrap__Af_5S"}
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
    

export default PrimaryLinkButton
