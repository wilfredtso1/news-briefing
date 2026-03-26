import React from 'react'
import type { JSX } from 'react/jsx-runtime'



// Component

        function RichTextArticle({
            text
        }: {
            text: string;
        }) {
            return (
                <article
                    className={"contentfulRichText_richText__rW7Oq contentfulRichText_sans__UVbfz"}
                    style={{
                        "--rich-text-font-config-font-size": "var(--font-size-200)",
                        "--rich-text-font-config-line-height": "var(--font-line-height-200)",
                        "--rich-text-font-config-font-family": "var(--font-family-sans)",
                        "--rich-text-font-config-font-variant-numeric": "normal",
                        "--rich-text-font-config-color": "inherit"
                    } as React.CSSProperties}
                >
                    <div
                        className={"contentfulRichText_bodyLimit__F5GOU"}
                        style={{
                            "--rich-text-limit-max-width": "none"
                        } as React.CSSProperties}
                    >
                        <p className={"contentfulRichText_paragraph___hjRE"}>
                            {text}
                        </p>
                    </div>
                </article>
            );
        }
    

export default RichTextArticle
