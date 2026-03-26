import React from 'react'
import type { JSX } from 'react/jsx-runtime'



    
// Component

        function InlineTextLink({
            label
        }: {
            label: string;
        }) {
            return (
                <a
                    className={"InlineTextLink_inlineLink__oN8YM InlineTextLink_colorInherit__oGlTG InlineTextLink_underlineOnHover__J78xW"}
                    target={"_self"}
                >
                    <span className={"InlineTextLink_linkContent__SYI4r"}>
                        <span
                            className={"typography_typography__Exx2D"}
                            style={{
                                "--typography-font": "var(--typography-sans-150-regular-font)",
                                "--typography-font-sm": "var(--typography-sans-150-regular-font)",
                                "--typography-letter-spacing": "var(--typography-sans-150-regular-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-150-regular-letter-spacing)",
                                "--typography-color": "var(--color-gray-800)"
                            } as React.CSSProperties}
                        >
                            {label}
                        </span>
                    </span>
                </a>
            );
        }
    

export default InlineTextLink
