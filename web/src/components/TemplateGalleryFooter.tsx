import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Img from './Img.tsx'
import ButtonLink from './ButtonLink.tsx'
import Footer from './Footer.tsx'


// Component

        function TemplateGalleryFooter({
            imageId,
            heading,
            description,
            buttonLabel,
            buttonVariant
        }: {
            imageId: string;
            heading: string;
            description: string;
            buttonLabel: string;
            buttonVariant: string;
        }) {
            return (
                <footer className={"TemplateGalleryFooter_footer__4mGBk"}>
                    <picture>
                        <Img id={imageId} />
                    </picture>
                    <aside>
                        <h2
                            className={"typography_typography__Exx2D heading_heading__OmVf6"}
                            style={{
                                "--typography-font": "var(--typography-sans-600-bold-font)",
                                "--typography-font-sm": "var(--typography-sans-700-bold-font)",
                                "--typography-letter-spacing": "var(--typography-sans-600-bold-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-700-bold-letter-spacing)",
                                "--typography-color": "inherit"
                            } as React.CSSProperties}
                        >
                            {heading}
                        </h2>
                        <span
                            className={"typography_typography__Exx2D"}
                            style={{
                                "--typography-font": "var(--typography-sans-200-regular-font)",
                                "--typography-font-sm": "var(--typography-sans-200-regular-font)",
                                "--typography-letter-spacing": "var(--typography-sans-200-regular-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-200-regular-letter-spacing)",
                                "--typography-color": "inherit"
                            } as React.CSSProperties}
                        >
                            {description}
                        </span>

                        <ButtonLink
                            label={buttonLabel}
                            variant={buttonVariant}
                        />
                    </aside>
                </footer>
            );
        }
    

export default TemplateGalleryFooter
