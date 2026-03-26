import React from 'react'
import type { JSX } from 'react/jsx-runtime'

import Downward_chevron from './icons/Downward_chevron.tsx'
import Language_translation_bubbles from './icons/Language_translation_bubbles.tsx'
import Downward_chevron_arrow from './icons/Downward_chevron_arrow.tsx'


// Component

        function LanguagePickerButton({
            buttonId,
            label
        }: {
            buttonId: string;
            label: string;
        }) {
            return (
                <button
                    id={buttonId}
                    className={"button_button__atjat button_buttonVariantTertiary__lrfOH button_buttonSizeM__NexGD"}
                    type={"button"}
                >
                    <span className={"languagePickerButton_button__QWrdE"}>
                        <span>
                            <Language_translation_bubbles />
                        </span>
                        <span>
                            {label}
                        </span>
                        <span
                            className={"typography_typography__Exx2D"}
                            style={{
                                "--typography-font": "var(--typography-sans-150-regular-font)",
                                "--typography-font-sm": "var(--typography-sans-150-regular-font)",
                                "--typography-letter-spacing": "var(--typography-sans-150-regular-letter-spacing)",
                                "--typography-letter-spacing-sm": "var(--typography-sans-150-regular-letter-spacing)",
                                "--typography-color": "inherit"
                            } as React.CSSProperties}
                        >
                            <Downward_chevron_arrow />
                        </span>
                    </span>
                </button>
            );
        }
    

export default LanguagePickerButton
