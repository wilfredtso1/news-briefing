import React from 'react'
import type { JSX } from 'react/jsx-runtime'



// Component

        function PrimaryActionButton({
            label
        }: {
            label: string;
        }) {
            return (
                <button
                    className={"button_button__atjat button_buttonVariantPrimary__mUFQZ button_buttonSizeM__NexGD"}
                    type={"button"}
                >
                    <span className={"templateDuplicateCta_templatesButton__fQ1N7"}>
                        <span>
                            {label}
                        </span>
                    </span>
                </button>
            );
        }
    

export default PrimaryActionButton
