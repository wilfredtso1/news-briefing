import React from 'react'
import type { JSX } from 'react/jsx-runtime'



    
// Component

        function CreatorLink({
            name
        }: {
            name: string;
        }) {
            return (
                <a style={{ color: "inherit", textDecoration: "none" }}>
                    <span
                        className={"typography_typography__Exx2D templatePreview_creatorName__mceW9"}
                        style={{
                            "--typography-font": "var(--typography-sans-50-regular-font)",
                            "--typography-font-sm": "var(--typography-sans-50-regular-font)",
                            "--typography-letter-spacing": "var(--typography-sans-50-regular-letter-spacing)",
                            "--typography-letter-spacing-sm": "var(--typography-sans-50-regular-letter-spacing)",
                            "--typography-color": "var(--color-black)"
                        } as React.CSSProperties}
                    >
                        {name}
                    </span>
                </a>
            );
        }
    

export default CreatorLink
