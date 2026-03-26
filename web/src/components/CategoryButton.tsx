import React from 'react'
import type { JSX } from 'react/jsx-runtime'



    
// Component

        function CategoryButton({
            icon,
            label
        }: {
            icon: React.ReactNode;
            label: string;
        }) {
            return (
                <a className={"button_button__atjat button_buttonVariantTertiary__lrfOH button_buttonSizeM__NexGD"}>
                    {icon}
                    <span
                        className={"typography_typography__Exx2D"}
                        style={{
                            "--typography-font": "var(--typography-sans-50-regular-font)",
                            "--typography-font-sm": "var(--typography-sans-50-regular-font)",
                            "--typography-letter-spacing": "var(--typography-sans-50-regular-letter-spacing)",
                            "--typography-letter-spacing-sm": "var(--typography-sans-50-regular-letter-spacing)",
                            "--typography-color": "inherit"
                        } as React.CSSProperties}
                    >
                        {label}
                    </span>
                </a>
            );
        }
    

export default CategoryButton
